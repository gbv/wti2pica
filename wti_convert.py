"""
.. module:: wti_convert_kxp
   :platform: Unix
   :synopsis: Ein Script zum Konvertieren von WTI-XML in (K10Plus) PICA+

.. moduleauthor:: Moritz Horn <moritz.horn@gbv.de>

.. version:: 0.1 (29.03.2019)

"""

import os
from lxml import etree
import json
import cgi
import pycountry
import html
import re
from urllib.parse import urlsplit
from pprint import pprint
import statistics
import logging
import datetime
import sys
import gzip
import time
import requests
import isbnlib

env = '.'
if 'VIRTUAL_ENV' in os.environ:
  env = os.environ['VIRTUAL_ENV']

class Constants(object):
  STATS_PATH = './statistics/'
  HISTORY_FNAME = 'last_run.json'
  OUTPUT_PATH = './output/'
  OUTPUT_FNAME = 'wti_pica'
  USAGE_STRING = "Usage: 'python3 wti_convert.py ['--stats_only'|'--no_stats'|'--update'] [--in directory/|/path/to/file] [--out directory/]"

# Logging

log_path = env + '/logs/'
current_date = '{:%Y-%m-%d}'.format(datetime.datetime.now())
logfname = 'logs_' + current_date + '.log'

logging.basicConfig(filename=log_path + logfname, level=logging.DEBUG)
log = logging.getLogger()
log.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s - %(message)s')
ch.setFormatter(formatter)
log.addHandler(ch)


def _match_isbns(isbn10, isbn13):
  """
  Versucht aus getrennten Listen von ISBN-10 und ISBN-13 Paare zu bilden.

  :param isbn10: Liste mit ISBN-10
  :type isbn10: list
  :param isbn13: Liste mit ISBN-13
  :type isbn13: list
  """
  pairs = []
  i10_matched = []

  for i13 in isbn13:
    short13 = i13[4:-2]
    match = False

    for index, i10 in enumerate(isbn10):
      short10 = i10[:-2]

      if short13 == short10:
        pairs.append({'004A': [{'0': i10}]})
        pairs.append({'004A': [{'0': i13}]})
        i10_matched.append(index)
        match = True
        break

    if match == False:
      pairs.append({'004A': [{'0': i13}]})

  for index, i10 in enumerate(isbn10):
    if index not in i10_matched:
      pairs.append({'004A': [{'0': i10}]})

  return pairs



def _process_tails(node):
  """
  Verarbeitet mögliche HTML-Tags in einem XML-Knoten

  :param node: Der zu untersuchende XML-Knoten
  :type node: etree._Element
  :returns: str

  """
  c_node = node.text

  tails = node.xpath('child::*')
  if tails is not None and len(tails) > 0:
    c_node = ''.join(("<" + child.tag + ">" + child.text + "</" + child.tag + ">" if child.tag is not None and child.tag in ["sub","sup"] and child.text is not None else "") if isinstance(child, etree._Element) else str(child) for child in node.xpath('child::*|text()'))

  return c_node



def _decide_material(dep, url, genres):
  """
  Diese Funktion generiert den Materialcode (002@) aus Angaben im XML.

  :param dep: Abhängigkeit
  :type dep: bool
  :param url: Wurde eine URL gefunden?
  :type url: bool
  :param genres: Liste von documentGenreCodes
  :type genres: list
  :returns: str -- der Materialcode

  """

  code = ["","","x"]

  if url:
    code[0] = 'O'

  else:
    code[0] = 'A'

  if dep:
    code[1] = 's'

  else:
    code[1] = 'a'

  return ''.join(code)



def process_document(document):
  """
  Diese Funktion extrahiert PICA+-Felder und Statistiken zu diesen aus dem XML

  :param document: Der XML-Knoten des Titels
  :type document: etree._Element
  :returns: list

  """

  xml_lang = '{http://www.w3.org/XML/1998/namespace}lang'
  dependend = True
  url_found = False
  record = []

  # Structure of Stats

  stats = {
    'genres':{
      'values': []
    },
    'types':{
      'values': []
    },
    'authors':{
      'num': 0,
      'with_aff': 0
    },
    'identifiers':{
      'num': 0,
      'isbn10': 0,
      'isbn13': 0,
      'isbnX': 0,
      'issn': 0,
      'eissn': 0
    },
    'lang':{
      'num': 0,
      'names': [],
      'error': 0,
      'iso3': 0,
      'iso2': 0
    },
    'pages':{
      'error': 0
    },
    'size':{
      'num': 0
    },
    'locations':{
      'num': 0,
      'types': [],
      'subtypes': []
    },
    'abstracts':{
      'num': 0,
      'tags': 0,
      'lang': []
    },
    'title':{
      'lang': "",
      'tags': 0,
      'alt': []
    },
    'conference':{
      'num': 0,
    },
    'copyright':{
      'num': 0
    },
    'publisher':{
      'num': 0,
      'place': 0
    },
    'date':{
      'values': []
    },
    'classifications':{
      'types': []
    },
    'subjects':{
      'values': []
    },
    'thesaurus':{
      'num': 0,
      'des': []
    }
  }

  # System Info

  system_info = document.find('systemInfo')

  metadata_cr = system_info.find('metadataCopyright')

  if metadata_cr is not None:
    metadata_cr = metadata_cr.find('dc:rights', system_info.nsmap)

    if metadata_cr is not None and metadata_cr.text is not None:
      md_cr = metadata_cr.text
      md_cr.replace("Copyright", "©")
      md_cr.replace("(c)", "©")

      record.append({'037I': [{'a': 'Metadaten: ' + md_cr}]})

  doc_id = system_info.find('documentID')

  if doc_id is not None and doc_id.text is not None:
    record.append({'007G': [{'i': "WTI"}, {'0': doc_id.text }]})

  else:
    log.error("No WTI-ID found!")
    return [record, stats]

  # Formal Info

  formal_info = document.find('formalInfo')

  document_def = formal_info.find('documentTypes').find('documentAdvancedType')

  ## DocumentGenres

  genre_groups = document_def.findall('documentGenreGroup')

  if genre_groups is not None:
    for genre_group in genre_groups:
      for genre in genre_group:
        stats['genres']['values'].append(genre.find('documentGenreCode').text)

  ## DocumentTypes

  type_groups = document_def.findall('documentTypeGroup')

  if type_groups is not None:
    for type_group in type_groups:
      for ty in type_group:
        stats['types']['values'].append(ty.find('documentTypeCode').text)

  ## Copyright

  doc_copyright = formal_info.find('copyright')

  if doc_copyright is not None:
    doc_copyright = doc_copyright.find('dc:rights', formal_info.nsmap)

    if doc_copyright is not None and doc_copyright.text is not None:
      doc_cr = doc_copyright.text
      stats['copyright']['num'] += 1
      doc_cr.replace("Copyright", "©")
      doc_cr.replace("(c)", "©")
      doc_cr.replace("(C)", "©")
      record.append({'037I': [{'a': 'Nutzungsrecht: ' + doc_cr}]})

  ## Sizes

  sizes = formal_info.find('sizes')

  if sizes is not None:
    for size in sizes:
      stats['size']['num'] += 1
      record.append({'034D': [{'a': size.text}]})

  ## Identifiers

  identifiers = formal_info.find('identifiers')
  isbn10 = []
  isbn13 = []
  journal = []
  issn = []
  eissn = []

  if identifiers is not None:
    for i in identifiers:
      sel_type = i.get('type')
      stats['identifiers']['num'] += 1

      if sel_type == 'isbn10':
        stats['identifiers'][sel_type] += 1
        isbn10.append(i.text)

      if sel_type == 'isbn13':
        stats['identifiers'][sel_type] += 1
        isbn13.append(i.text)

      if sel_type == 'isbn':
        if isbnlib.is_isbn10(i.text):
          stats['identifiers']['isbn10'] += 1
          isbn10.append(i.text)
        elif isbnlib.is_isbn13(i.text):
          stats['identifiers']['isbn13'] += 1
          isbn13.append(i.text)
        else:
          stats['identifiers']['isbnX'] += 1
          log.warning('Invalid isbn in TEMA' + doc_id.text + ':' + i.text)

      if sel_type == 'issn':
        stats['identifiers'][sel_type] += 1
        journal.append(i.text)
        issn.append(i.text)

      if sel_type == 'eissn':
        stats['identifiers'][sel_type] += 1
        journal.append(i.text)
        eissn.append(i.text)

  ## Languages

  languages = formal_info.find('documentLanguages')

  for lang in languages:
    langcode = lang.find('languageCodes').find('code')
    stats['lang']['num'] += 1
    stats['lang']['names'].append(langcode.text)

    if langcode.get('iso') == '639-1':
      stats['lang']['iso2'] += 1
      al2 = langcode.text.lower()

      if al2 == 'sp':
        stats['lang']['error'] += 1
        al2 = 'es'

      try:
        lang_obj = pycountry.languages.get(alpha2=al2)

      except:
        stats['lang']['error'] += 1

      else:
        if lang_obj is not None:
          record.append({'010@': [{'a': lang_obj.bibliographic}]})

    elif langcode.get('iso') == '639-2':

      stats['lang']['iso3'] += 1
      record.append({'010@': [{'a': langcode.text.lower()}]})

  ## Locations

  locations = formal_info.find('locations')

  if locations is not None:

    for loc in locations:
      stats['locations']['num'] += 1
      loc_type = loc.get('type')
      loc_subtype = loc.get('subtype')

      stats['locations']['types'].append(loc_type)
      stats['locations']['subtypes'].append(loc_subtype)

      if loc_type == 'url':
        url_text = loc.text
        url_found = True
        record.append({'017D': [{'u': url_text}]})

        if loc_subtype == 'doi':
          doi = urlsplit(url_text).path[1:]
          record.append({'004V': [{'0': doi}]})

  # Bibliographic Info

  bibliographic_info = document.find('bibliographicInfo')

  if bibliographic_info.get('dependend') == 'false':
    dependend = False

  ## Title

  title = bibliographic_info.find('dc:title', bibliographic_info.nsmap)

  if title is not None:
    clean_title = title.text
    tails = title.xpath('child::*')

    if tails is not None and len(tails) > 0:
      clean_title = _process_tails(title)
      stats['title']['tags'] += 1

    if clean_title:
      record.append({'021A': [{'a': clean_title}]})
      stats['title']['lang'] = title.get(xml_lang)

    else:
      log.warning("No Title:")
      log.warning(doc_id.text)

  ## Alternative Titles

  alt_titles = bibliographic_info.find('alternativeTitles')

  if alt_titles is not None:
    for alt in alt_titles:
      alt_lang = alt.get(xml_lang)
      clean_alt = _process_tails(alt)

      if alt_lang and clean_alt:
        stats['title']['alt'].append(alt_lang)
        record.append({'021G': [{'a': clean_alt}]})

  ## Abstracts

  abstracts = bibliographic_info.find('abstracts')

  if abstracts is not None:
    for abstract in abstracts:
      cleaned_abstract = abstract.text
      tails = abstract.xpath('child::*')

      if tails is not None and len(tails) > 0:
        stats['abstracts']['tags'] += 1
        cleaned_abstract = _process_tails(abstract)

      abs_lang = abstract.get(xml_lang)

      stats['abstracts']['num'] += 1
      stats['abstracts']['lang'].append(abs_lang)

      copyright = abstract.get('copyright')

      if cleaned_abstract and copyright is not None:
        cleaned_abstract += (' [' + copyright + ']')

      if cleaned_abstract:
        record.append({'047I': [{'a': cleaned_abstract}]})

  ## Authors

  ### Affiliations

  aff_temp = bibliographic_info.find('authorsAffiliations')
  affiliations = []

  if aff_temp is not None:
    for aff in aff_temp:
      stats['authors']['with_aff'] += 1
      affiliations.append(aff.find('affiliation').text)

  ### Authors

  authors = bibliographic_info.find('creators')

  if authors is not None:
    for index, author in enumerate(authors):
      name = author.find('dc:creator', authors.nsmap)

      if name is not None and len(name) > 0:
        stats['authors']['num'] += 1
        name = name.text.split(", ")

        author_fields = []

        if len(name) > 1:
          author_fields.append({'d': name[1]})

        author_fields.append({'a': name[0]})

        #if aff_temp is not None and len(affiliations) > index:
          #author_fields.append({'p': affiliations[index]})

        author_fields.append({'B': "VerfasserIn"})
        author_fields.append({'4': "aut"})

        if index == 0:
          record.append({'028A': author_fields})

        else:
          record.append({'028C': author_fields})

  ## Material Code

  material_code = _decide_material(dependend, url_found, stats['genres']['values'])

  record.append({'002@': [{'0': material_code}]})

  ## Additional Info

  additional_info = bibliographic_info.find('additionalDocumentInfo')

  article_info = additional_info.find('articleInfo')
  journal_info = additional_info.find('journalInfo')

  ### Conference Info

  conference_info = additional_info.find('conferenceInfos')

  if conference_info is not None:
    conferences = conference_info.findall('conferenceInfo')

    for conf in conferences:
      stats['conference']['num'] += 1
      conf_date_parts = ["",""]

      for date in conf.findall('dc:date', conf.nsmap):
        if date.get('type') == 'begin':
          conf_date_parts[0] = date.text.replace("-", ".")

        elif date.get('type') == 'end':
          conf_date_parts[1] = date.text.replace("-", ".")

      conf_date = '-'.join(conf_date_parts)
      conf_place = conf.find('place')
      conf_names = conf.findall('name')

      for conf_name in conf_names:
        if conf_name.text is not None:
          conf_field = []
          conf_split = conf_name.text.split(', ')
          conf_field.append({'a': conf_split[0]})

          if len(conf_split) == 2:
            conf_field.append({'j': conf_split[1]})

          if conf_place is not None and conf_place.text is not None:
            conf_field.append({'k': conf_place.text})

          if not conf_date == "-":
            conf_field.append({'p': conf_date})

          record.append({'030F': conf_field})


  ## Publication Info

  publication_info = bibliographic_info.find('publicationInfo')
  publ_date = publication_info.find('dcterms:Issued', publication_info.nsmap)

  if journal_info is not None:
    journal_title = ""
    journal_year = ""
    journal_vol = ""
    journal_iss = ""

    if journal_info.find('dc:title', journal_info.nsmap) is not None and journal_info.find('dc:title', journal_info.nsmap).text is not None:
      journal_title = journal_info.find('dc:title', journal_info.nsmap).text

    elif article_info is not None and article_info.find('dc:title', article_info.nsmap) is not None and article_info.find('dc:title', article_info.nsmap).text is not None:
      journal_title = article_info.find('dc:title', article_info.nsmap).text

    if journal_info.find('volumeNumber') is not None and journal_info.find('volumeNumber').text is not None:
      journal_vol = journal_info.find('volumeNumber').text

    if journal_info.find('issueNumber') is not None and journal_info.find('issueNumber').text is not None:
      journal_iss = journal_info.find('issueNumber').text

    if journal_info.find('coverDate') is not None and journal_info.find('coverDate').text is not None:
      journal_date = journal_info.find('coverDate').text

    if not dependend:
      if journal_title:
        series_fields = [{'a': journal_title}]

        if journal_vol:
          series_fields.append({'l': journal_vol})

        record.append({'036E': series_fields})

      if len(isbn10) > 0 and len(isbn13) > 0:
        isbn_pairs = _match_isbns(isbn10, isbn13)

        for pair in isbn_pairs:
          record.append(pair)

      elif len(isbn13) > 0:
        for isbn in isbn13:
          record.append({'004A': [{'0': isbn}]})

      elif len(isbn10) > 0:
        for isbn in isbn10:
          record.append({'004A': [{'0': isbn}]})

    elif dependend:
      if journal_title is not None:
        pages = ""
        if article_info is not None:
          if article_info.find('pages') is not None and article_info.find('pages').text is not None:
            splitpages = article_info.find('pages').text.split("-")

            if len(splitpages) == 2:
              pages = article_info.find('pages').text

            else:
              stats['pages']['error'] += 1

        precise_infos = []
        journal_fields = []
        greater_fields = [{'c': "In"}]

        if journal_title:
          journal_fields.append({'a': journal_title})
          greater_fields.append({'a': journal_title})

        if journal_vol:
          precise_infos.append({'d': journal_vol})

        if journal_year:
          precise_infos.append({'j': journal_year})

        else:
          precise_infos.append({'j': publ_date.text})

        if journal_iss:
          precise_infos.append({'e': journal_iss})

        if pages:
          precise_infos.append({'h': pages})

        record.append({'031A': precise_infos})

        if len(journal) > 0:
          if material_code == 'Osx':
            for i in eissn:
              journal_fields.append({'0': i})
              greater_fields.append({'C': "ISSN"})
              greater_fields.append({'6': i})

          elif material_code == 'Asx':
            for i in issn:
              journal_fields.append({'0': i})
              greater_fields.append({'C': "ISSN"})
              greater_fields.append({'6': i})

        elif len(isbn13) > 0:
          for isbn in isbn13:
            journal_fields.append({'i': isbn})
            greater_fields.append({'C': "ISBN"})
            greater_fields.append({'6': isbn})

        elif len(isbn10) > 0:
          for isbn in isbn10:
            journal_fields.append({'i': isbn})
            greater_fields.append({'C': "ISBN"})
            greater_fields.append({'6': isbn})

        #record.append({'027D': journal_fields})

        record.append({'039B': greater_fields})

  ### Publisher

  publisher = publication_info.find('dc:publisher', publication_info.nsmap)
  publ_place = publication_info.find('publicationPlace')

  if publisher is not None and publisher.text is not None:
    stats['publisher']['num'] += 1
    publ_fields = []

    if publ_place is not None and publ_place.text is not None:
      stats['publisher']['place'] += 1
      publ_fields.append({'p': publ_place.text})

    publ_fields.append({'n': publisher.text})
    record.append({'033A': publ_fields})

  if publ_date is not None:
    stats['date']['values'] = publ_date.text
    record.append({'011@': [{'a': publ_date.text}]})

  # Classification Info

  classification_info = document.find('classificationInfo')

  if classification_info is not None:
    classifications = classification_info.find('classifications')

    if classifications is not None:
      for c in classifications:
        c_name = c.get('classificationName')
        stats['classifications']['types'].append(c_name)
        nots = [{'i': c_name}]

        for cl in c:
          nots.append({'a': cl.find('code').text})
        record.append({'045X': nots})

    subjects = classification_info.find('subjects')

    if subjects is not None:
      for sub in subjects:
        if sub.text is not None:
          stats['subjects']['values'].append(sub.text)
          record.append({'044N': [{'S': 's'},{'a': sub.text}]})

  # Functional Info

  functional_info = document.find('functionalInfo')
  thesaurus = functional_info.find('thesaurusTerms')

  ## Thesaurus

  if thesaurus is not None:
    temp_synonyms = thesaurus.find('synonyms')
    synonyms = []
    syn_group = []

    if temp_synonyms is not None:
      for index, syn in enumerate(temp_synonyms):
        syn_type = syn.get('type')
        syn_lang = syn.get(xml_lang)
        stats['thesaurus']['num'] += 1

        if index == 0:
          syn_group.append({'S': "s"})

        if syn_type == 'DES' or syn_type == 'SYN':
          stats['thesaurus']['des'].append(syn.text)

          if index > 0 and ( temp_synonyms[index-1].get('type') == 'SUP' or ( syn_lang == 'DE' and temp_synonyms[index-1].get(xml_lang) == 'EN') ):
            synonyms.append(syn_group)
            syn_group = []
            syn_group.append({'S': "s"})

        if syn_lang == 'DE':
          syn_group.append({'a': syn.text})

        if index == (len(temp_synonyms) - 1):
          synonyms.append(syn_group)

      for group in synonyms:
        record.append({'044N': group})

  ## Free Terms

  free_terms = functional_info.find('freeTerms')

  if free_terms is not None:
    for ft in free_terms:
      if ft.text is not None:
        record.append({'044N': [{'S': "s"}, {'a': ft.text}]})

  return [record, stats]


def write_to_file(record, num_record, fpath):
  """
  Diese Funktion liest eine Liste von PICA-Feldern und schreibt diese im PICA-Internformat in eine Datei.

  Struktur eines `records`::

    [
      {
        '031N': [
          {'d': "15"},
          {'j':"2004"}
        ]
      },
      {
        '002@': [
          {'0': "Osx"}
        ]
      }
    ]

  :param record: die Liste mit PICA-Feldern
  :type record: list
  :param num_record: die laufende Titelanzahl in der aktuellen Datei
  :type num_record: int
  :param fpath: der Dateiname inklusive Pfad
  :type fpath: str
  """
  record = sorted(record, key=lambda x: list(x.keys())[0])

  with open(fpath, 'a+') as f:
    f.write('<1D>' + "\n")
    f.write('##TitleSequenceNumber ' + str(num_record) + "\n")

    for field in record:
      field_name = list(field.keys())[0]
      f.write('<1E>')
      f.write(field_name + " ")

      for subfield in field[field_name]:
        subfield_name = list(subfield.keys())[0]
        f.write('<1F>')
        f.write(subfield_name)
        if type(subfield_name) is str and subfield[subfield_name] is not None:
          if type(subfield[subfield_name]) is str:
            f.write(subfield[subfield_name])

          else:
            log.warning(field_name)
            log.warning(subfield_name)
            log.warning(subfield)

        else:
          log.warning(field_name)
          log.warning(subfield_name)
          log.warning(subfield)

      f.write("\n")
    f.write("\n")


def _max_val(d):
  """
  Bestimmt den Maximalwert in einem Dictionary und gibt in mit dem dazugehörigen Key zurück.
  
  :param d: Das zu untersuchende Python-Dictionary
  :type d: dict
  :returns: list
  """

  v=list(d.values())
  k=list(d.keys())

  if len(v) > 0 and len(k) > 0:
    return [k[v.index(max(v))], max(v)]

  else:
    return [None,None]


def _min_val(d):
  """
  Bestimmt den Minimalwert in einem Dictionary und gibt in mit dem dazugehörigen Key zurück.
  
  :param d: Das zu untersuchende Python-Dictionary
  :type d: dict
  :returns: list
  """

  v=list(d.values())
  k=list(d.keys())

  if len(v) > 0 and len(k) > 0:
    return [k[v.index(min(v))], min(v)]

  else:
    return [None,None]


def prepare_stats(stats, stats_path):
  """
  Diese Funktion erzeugt CSV-Dateien für die Inhalte eines Dictionaries mit Statistiken.

  Struktur der `stats`::

    {
      'lang':{
        'num':{'1': 20, '0': 50, '2': 10},
        'names':{'de': 30, 'en': 10}
      },
      'genres':{
        'values':{'J': 300, 'CA': 80, 'B': 10}
      }
    }

  :param stats: Die übergebenen Statistiken
  :type stats: dict.
  """
  
  statsSubf = current_date + '/'
  os.makedirs(stats_path + statsSubf, exist_ok=True)
  
  with open(stats_path + statsSubf + "topic_stats.csv", 'w+') as sf:
    sf.write("name,num_keys,max_key,max_occ,max_occ_key,min_key,min_occ,min_occ_key,mean\n")

    for topic, value in stats.items():
      if type(value) is dict:
        for sub_topic, sval in value.items():
          row_name = topic + "_" + sub_topic

          if type(sval) is dict:
            max_key, max_val = _max_val(sval)
            min_key, min_val = _min_val(sval)
            vals = list(sval.values())
            keys = list(sval.keys())
            int_keys = []
            num_zero = ""
            is_string = 0
            kv_list = []
            mean = -1

            with open(stats_path + statsSubf + row_name + ".csv", 'w+') as subfield_stats:
              subfield_stats.write("value,num\n")

              for k, v in sval.items():
                if k is not None and v is not None:
                  kv_list.append({k: v})

                if k == "0":
                  num_zero = str(v)

              kv_list = sorted(kv_list, key=lambda x: list(x.values())[0], reverse=True)

              if len(kv_list) > 10:
                kv_list = kv_list[:10]

              for item in kv_list:
                sf_keys = list(item.keys())
                sf_values = list(item.values())
                subfield_stats.write(sf_keys[0] + "," + str(sf_values[0]) + "\n")

            if len(vals) > 0:
              for k in keys:
                try:
                  int_keys.append(int(k))

                except:
                  is_string = 1

              if is_string == 0:
                sorted_keys = sorted([int(x) for x in int_keys])

                summage = 0

                for k, v in sval.items():
                  summage += int(k)*v

                mean = round(summage/stats['num'], 2)

                sf.write(row_name + ",")
                sf.write(str(len(keys)) + ",")

                if max_key is not None:
                  sf.write(str(sorted_keys[-1]) + "," + str(max_val) + "," + str(max_key))

                else:
                  sf.write(",")

                sf.write(",")

                if min_key is not None:
                  sf.write(str(sorted_keys[0]) + "," + str(min_val) + "," + str(min_key))

                else:
                  sf.write(",")

                sf.write(",")

                if num_zero:
                  sf.write(num_zero)

                sf.write(",")

                if mean != -1:
                  sf.write(str(mean))

                sf.write("\n")

          else:
            log.warning("Skipped subtopic " + sub_topic + " of " + topic + "!")
      elif topic != 'num':
        log.warning("Skipped topic " + topic + "!")


# Handle XML files

def handle_xml(xml_path, xml_filename, num_files, stats_only, is_update, out_path):
  """
  Parst die XML-Dateien und kumuliert deren Statistiken.

  :param xml_path: Der Pfad zu den XML-Dateien
  :type xml_path: str
  :param xml_filename: Ein eventuell gegebener spezifischer Dateiname in dem Verzeichnis
  :type xml_filename: str
  :param num_files: Die Gesamtanzahl an XML-Dateien in dem Verzeichnis
  :type num_files: int
  :param stats_only: Eine Flag, ob die Ergebnisse mit `write_to_file()` geschrieben werden sollen
  :type stats_only: bool
  :param is_update: Eine Flag, ob die Ergebnisse in ein mit dem Datum benannten Unterverzeichnis gespeichert werden sollen
  :type stats_only: bool
  :param out_path: Ein manuell angegebener Output-Pfad
  :type out_path: str
  :returns: list
  """

  all_stats = {
    'num': 0
  }
  num_warn = 0
  cur_file = 0

  for file in os.listdir(xml_path):

    if (not xml_filename and file.endswith((".xml",".XML","XML.gz"))) or (xml_filename and file == xml_filename):

      nzfile = None
      no_gz_ext = None

      if file.endswith("XML.gz"):

        zfile = os.path.join(xml_path, file)
        no_gz_ext = file[:file.rfind('.')]
        nzfile = os.path.join(xml_path, no_gz_ext)

        if not os.path.exists(nzfile):
          with gzip.GzipFile(zfile, 'rb') as inF:
            with open(nzfile, 'wb') as outF:
              s = inF.read()
              outF.write(s)
        else:
          continue

      else:
        nzfile = os.path.join(xml_path, file)
        no_gz_ext = file

      cur_file += 1
      no_ext = no_gz_ext[:no_gz_ext.rfind('.')]

      base_path = Constants.OUTPUT_PATH

      if out_path:
        base_path = out_path


      if is_update:
        datePath = 'upd_' + current_date +'/'
        os.makedirs(base_path + datePath, exist_ok=True)
        base_path = base_path + datePath

      ext_fname = no_ext + "_" + Constants.OUTPUT_FNAME
      ext_path = base_path + no_ext + "/"
      combined = ext_path + ext_fname

      if xml_filename:
        num_files = 1

        if not stats_only:
          os.makedirs(ext_path, exist_ok=True)

          if os.path.isfile(combined):
            os.rename(combined, combined + ".prev")

      else:
        combined = base_path + ext_fname

        if not stats_only:
          if os.path.isfile(combined):
            os.rename(combined, combined + ".prev")

      docs_in_file = 0

      log.debug("processing: " + nzfile + " (" + str(cur_file) + "/" + str(num_files) + ")")

      try:
        for event, document in etree.iterparse(nzfile, load_dtd=True, no_network=False, tag="document"):
          record, stats = process_document(document)
          docs_in_file += 1
          all_stats['num'] += 1

          if len(record) > 0:
            for topic, values in stats.items():
              if type(values) is dict:
                if topic not in all_stats:
                  all_stats[topic] = {}

                for k, val in values.items():
                  if k not in all_stats[topic]:
                    all_stats[topic][k] = {}

                  if type(val) is list:
                    for v in val:
                      if v not in all_stats[topic][k]:
                        all_stats[topic][k][v] = 1

                      else:
                        all_stats[topic][k][v] += 1

                  elif type(val) is int:
                    if str(val) not in all_stats[topic][k]:
                      all_stats[topic][k][str(val)] = 1

                    else:
                      all_stats[topic][k][str(val)] += 1

                  elif type(val) is str:
                    if val not in all_stats[topic][k]:
                      all_stats[topic][k][val] = 1

                    else:
                      all_stats[topic][k][val] += 1

                  else:
                    log.error("Could not process stats for " + topic + " -> " + k)

              else:
                log.error("Problem identifying stats for " + topic)


            if not stats_only:
              try:
                write_to_file(record, docs_in_file, combined)

              except:
                log.error("Problem writing to file.")
                log.error(sys.exc_info()[0])

          else:
            log.warning("Skipped record #" + str(docs_in_file) + "..")

          document.clear()

        log.debug("Processed " + str(docs_in_file) + " documents in file " + file + "!")

      except etree.XMLSyntaxError as e:
        num_warn += 1
        log.error("Error while parsing: " + no_ext)
        log.error(e)

      except:
        log.error("Unexpected error in " + no_ext + ": " + str(sys.exc_info()[0]))
        raise
        pass

      if os.path.exists(nzfile) and os.path.exists(nzfile + ".gz"):
        os.remove(nzfile)

  return [all_stats, num_warn, cur_file]

# MAIN

def main(argv):
  """
  Entpackt Dateien und startet die Konvertierung und Erstellung von Statistiken
  
  :param argv: Die beim Programmstart übergebenen Parameter
  :type argv: list
  """
  xml_filename = ""
  xml_path = ""
  out_path = ""
  no_ext = ""
  num_warn = 0
  num_files = 0
  adjusted_stats_path = Constants.STATS_PATH
  stats_only = False
  no_stats = False
  is_update = False
  last_run = {}

  os.nice(1)
  
  if '--help' in argv or '-h' in argv:
    print(Constants.USAGE_STRING)
    sys.exit()
      
  for idx, arg in enumerate(argv):
    if arg == '--in' and len(argv) >= idx+1 and os.path.exists(argv[idx+1]):
      if not xml_path and not xml_filename:
        xml_path = os.path.split(argv[idx+1])[0]
        xml_filename = os.path.split(argv[idx+1])[1]
        
      else:
        print(argv)
        log.error("More than one import path was supplied!")
        sys.exit()

    if arg == '--out' and len(argv) >= idx+1:
      if not out_path and os.path.exists(argv[idx+1]):
        out_path = argv[idx+1]
      else:
        print(argv)
        log.error("Output path does not exist, or multiple paths were supplied!")
        sys.exit()

  if not xml_path:
    log.debug("No path given, using current directory..")
    xml_path = '.'

  if xml_filename and not xml_filename.endswith(('.xml', '.XML','.XML.gz')):
    log.error("Filename has to end with .xml/.XML/.XML.gz")
    sys.exit()

  start_time = int(time.time())
  log.debug('Start: {:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now()))
  
  if not xml_filename:
    for file in os.listdir(xml_path):
      if file.endswith((".xml",".XML",".XML.gz")):
        if file.endswith(".XML.gz"):
          
          zfile = os.path.join(xml_path, file)
          no_gz_ext = file[:file.rfind('.')]
          nzfile = os.path.join(xml_path, no_gz_ext)
          
          if not os.path.exists(nzfile):
            num_files += 1
          
          else:
            log.debug("Decompressed file already exists..")
        else:
          num_files += 1
            
  else:
    if xml_filename.endswith(".XML.gz"):
      log.debug("Handling compressed file " + xml_filename)
      
      zfile = os.path.join(xml_path, xml_filename)
      no_gz_ext = xml_filename[:xml_filename.rfind('.')]
      nzfile = os.path.join(xml_path, no_gz_ext)
      
      if not os.path.exists(nzfile):
        
        log.debug("Decompressing file " + xml_filename)
        
        with gzip.GzipFile(zfile, 'rb') as inF:
          with open(nzfile, 'wb') as outF:
            s = inF.read()
            outF.write(s)
            
      else:
        log.debug("Found existing decompressed file..")
          
      xml_filename = no_gz_ext
  

  if not xml_filename:
    log.debug("Found " + str(num_files) + " XML files!")
    
  else:
    num_files = 1

  if '--stats_only' in argv:
    log.debug("Only generating stats (not writing any output files)..")
    stats_only = True

  if '--no_stats' in argv:
    log.debug("Skipping stat generation..")
    no_stats = True

  if '--update' in argv:
    log.debug("Writing to subfolder..")
    is_update = True

  gathered_stats, num_warn, cur_file = handle_xml(xml_path, xml_filename, num_files, stats_only, is_update, out_path)

  if xml_filename:
    if cur_file == 0:
      log.error("File not found!")

    else:
      no_ext = xml_filename[:xml_filename.rfind('.')]

  if not no_stats and cur_file > 0:
    if xml_filename:
      adjusted_stats_path += no_ext + "/"

    os.makedirs(adjusted_stats_path, exist_ok=True)
    log.debug("Generating stats..")

    try:
      prepare_stats(gathered_stats, adjusted_stats_path)

    except:
      log.error("Unexpected error creating stats:", sys.exc_info()[0])

  run_time = str(datetime.timedelta(seconds=(int(time.time()) - start_time)))
  last_run['date'] = current_date
  last_run['runtime'] = run_time
  last_run['records'] = gathered_stats['num']
  last_run['files'] = cur_file

  log.debug('End: {:%Y-%m-%d %H:%M:%S}'.format(datetime.datetime.now()))
  log.debug('Processed ' + str(gathered_stats['num']) + " records in " + str(cur_file) + " files!")

  if num_warn > 0:
    log.warning('Problems with standard DTD: ' + str(num_warn))
    last_run['warnings'] = num_warn

  with open("last_run.json", "w+") as lr:
    json.dump(last_run, lr)

if __name__ == "__main__":
    main(sys.argv)




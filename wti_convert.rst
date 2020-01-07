.. WTI2PICA+ documentation master file, created by
   sphinx-quickstart on Wed Feb 15 15:14:00 2017.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

WTI2PICA+ - Dokumentation
=====================================

.. toctree::
   :maxdepth: 2

Mögliche Parameter
==================

* '--help': Übersicht über die verfügbaren Parameter anzeigen
* '--stats_only': Es werden nur Statistiken generiert, aber keine PICA-Dateien
* '--no_stats': Generierung von Statistiken überspringen.
* '--in': Pfad zu einem spezifischen Ordner (für mehrere Dateien) oder vollständiger Dateipfad für eine einzige Datei (Standardort ist der aktuelle Ordner)
* '--out': Pfad zu einem Ordner, in den die fertigen Records gespeichert werden sollen
* '--update': Die neuen Dateien werden in einen Unterordner im Output-Verzeichnis (standardmäßig in '.output/', oder explizit per '--out' definiert) mit dem aktuellen Datum als Namen geschrieben

Funktionen
==========

.. automodule:: wti_convert
   :members:
   :private-members:


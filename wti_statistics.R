require(ggplot2)
library(scales)

generalStats <- read.csv('~/WTI/statistics/2018-10-22/topic_stats.csv')
files = list.files(path="~/WTI/statistics/2018-10-22/", pattern="*.csv")

localenv <- environment()
lapply(files, function(x){
  fieldname <- x
  splitstr <- unlist(strsplit(fieldname, ".", fixed=TRUE))
  combined <- paste('~/WTI/statistics/', fieldname, sep="")
  genreStats <- read.csv(combined)
  if(fieldname != "topic_stats.csv"){
    genreStats <- genreStats[order(genreStats$num,decreasing = TRUE),]
    print(ggplot(genreStats, aes(reorder(value,-num),num), environment = localenv) 
      + geom_bar(stat="identity")
      + scale_y_continuous(labels=comma) 
      + xlab("Ausprägung") 
      + ylab("Vorkommnisse") 
      + ggtitle(splitstr[[1]])
    #  + geom_text(aes(y = num + 10,label=num), size=3, vjust=0)
      + theme(axis.text.x = element_text(angle = 45, vjust = 1, hjust=1))
    )
    filename <- paste('~/WTI/statistics/2018-10-22/', splitstr[[1]], ".pdf", sep="")
    ggsave(filename)
    message("saved ",filename)
    dev.off()
  }else{
    
  }
})

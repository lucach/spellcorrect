# Spell corrector

"Spell corrector" is a system designed to correct misspellings in Italian language. Statistical data are retrieved from the italian version of Wikipedia.

## Report
To read the story behind this project and to understand why it works, you should read [this](https://raw.githubusercontent.com/lucach/spellcorrect/master/thesis/main.pdf) (in Italian).

## Usage

- **End users**: http://spellcorrect.chiodini.org/
- API (for developers): http://api.spellcorrect.chiodini.org/

## API Definition

### Queries
Queries are in the form ```http://api.spellcorrect.chiodini.org/correct/<str>```, where ```<str>``` is the query you want to perform.

### Responses
Responses are JSON encoded and contain the following data:
- ```cache```: whether the result has been served from the cache
- ```input```: input string
- ```corrected```: corrected string
- ```elapsed_time```: total computational time needed to serve your response
- ```queries```: total number of queries needed to choose the best correction

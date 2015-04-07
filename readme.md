Spell corrector
===============

"Spell corrector" is a system designed to correct misspellings in Italian language. Statistical data are retrieved from Wikipedia-it.

Usage
-----
**Beta** version: http://beta.it-spellcorrect.appspot.com/correct/<query>
Example: http://beta.it-spellcorrect.appspot.com/correct/eccezzione

API Responses
-----
** Warning! Responses layout may change at any time**
Responses are JSON encoded and contain following data:
- cache: whether the result has been served from the cache
- input: input query
- corrected: corrected query
- init_time: debug information, time in ISO format of when the appengine instance started

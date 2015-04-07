#!flask/bin/python
from flask import Flask, jsonify, abort, request, make_response, url_for

def start():
    app = Flask(__name__)
    return app

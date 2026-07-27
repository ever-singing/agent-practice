from flask import Flask

app = Flask(__name__)


@app.route("/")
def home():
    return "这是首页"


@app.route("/hello")
def hello():
    return "这是 hello 页面"


app.run(port=5000)

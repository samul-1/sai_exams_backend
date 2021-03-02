import json
import subprocess

from django.http import HttpResponse
from django.shortcuts import render

#!
from django.views.decorators.csrf import csrf_exempt


#!
@csrf_exempt
def evaluate_program(request):
    # if request.method == "GET":
    # program = json.loads(
    #     request.body.decode("utf-8")
    # )  # user's submission is in request body

    program = "function max(a) { return a.map(r=>r.nick!=='aaa' )}"
    test_cases = [
        {
            "input": "[{username: 'john', age: 22, nick: 'aaa'}, {username: 'alice', age: 32, nick: 'bb'}]"
        }
    ]

    res = subprocess.check_output(
        [
            "node",
            "jsplatform/node/runUserProgram.js",
            program,
            json.dumps(test_cases),
        ]
    )
    res = json.loads(res)
    return HttpResponse(res)

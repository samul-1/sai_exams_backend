// The VM2 module allows to execute arbitrary code safely using a sandboxed, secure virtual machine
const {VM} = require('vm2')

// set timeout to 1000ms to prevent endless loops from running forever
const safevm = new VM({
    timeout: 1000,
})

// takes in an array or strings; returns a string of comma separated values enclosed in parentheses
// used to convert an array of parameters to a string that can be appended to a function name to make a function call
function listToCSVString(list) {
    let str = '('
    for(parameter of list) {
        str += parameter + ','
    }
    str = str.slice(0, -1) + ')'
    return str
}

// takes in a string containing a function and a string representing its parameters; returns a string
// containing the definition of the function followed by a call to it with the given parameters
function functionToRunnable(func, params) {
    // look for the word 'function' followed by a string and a set of parentheses
    const funcName = process.argv[2].split(/^function ([^\(]*)\([^\)]*\)/)[1]
    return func += '\n' + funcName + params
}

// serializes js Error to JSON (the native Error cannot be serialized with JSON.stringify)
function stringifyError(err, filter, space) {
    var plainObject = {};
    Object.getOwnPropertyNames(err).forEach(function(key) {
      plainObject[key] = err[key]
    })
    return JSON.stringify(plainObject, filter, space)
  }

// process arguments
const userProgram = process.argv[2]
const testCases = JSON.parse(process.argv[3])

// will hold a list of test cases ran together with the given outputs
const outcome = []

for(const testCase of testCases) {
    // todo see if you can use a better split regex than \s
    parameters = testCase.input.split(/%%/) // get the input parameters for this test case
    paramString = listToCSVString(parameters) // get param string to append to function name

    const userProgramRunnable = functionToRunnable(userProgram, paramString)
    let res
    try {
        // console.log(`RUNNABLE:\n ${userProgramRunnable}\n END RUNNABLE`)

        // run user program against test case input
        res = safevm.run(userProgramRunnable)
        // if program returns undefined, use "undefined" (string) to mark that result, as you can't have
        // and object's property set to undefined and stringify it (property won't show up at all)
        // todo see if you can just omit res property when a program returns undefined
        res = typeof(res) == "undefined" ? "undefined" : res

        // push test case details to output list
        outcome.push({
            parameters,
            res,
        })
    } catch(error) {
        outcome.push({
            parameters,
            error: stringifyError(error, null, ' '),
        })
        // console.log(error)
    }
}

// output outcome details to console for Django to collect them
console.log(JSON.stringify(outcome))

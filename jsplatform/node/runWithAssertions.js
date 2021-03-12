/*
usage: 
node runWithAssertions.js programCode assertions

arguments:
programCode is a STRING containing a js program
assertions is an ARRAY of strings representing assertions made using node assertions


output: 
an array printed to the console (and collected by Django via subprocess.check_output()) where each entry 
corresponds to an assertion and is an object:
{ 
    id: Number,
    assertion: String,
    public: Boolean,
    passed: Boolean,
    error: String,
} 
where id is the id of the assertion (as in the Django database),
assertion is the string containing the assertion verbatim,
public indicates whether the assertion is to be shown to the user or it's secret,
passed represents the outcome of running the assertion on the program,
and error is only present if the assertion failed
*/


// The VM2 module allows to execute arbitrary code safely using a sandboxed, secure virtual machine
const {VM} = require('vm2')
// set timeout to 1000ms to prevent endless loops from running forever
const safevm = new VM({
    timeout: 1000,
    sandbox: {
        require,
    }
})

// utility function to turn Error data to strings
function stringifyError(err, filter, space) {
    var plainObject = {};
    Object.getOwnPropertyNames(err).forEach(function(key) {
      plainObject[key] = err[key]
    })
    return JSON.stringify(plainObject, filter, space)
}

const userCode = process.argv[2]

const assertions = JSON.parse(process.argv[3])
/*
[
    {
        id: 1,
        assertion: 'assert.strictEqual(max(1,2),2)',
        public: true,
    },    
    {
        id: 2,
        assertion: 'assert.strictEqual(max(22,10),22)',
        public: true,
    },    
    {
        id: 3,
        assertion: 'assert.strictEqual(max(-1,0),0)',
        public: false,
    },
]
*/

// turn array of strings representing assertion to a series of try-catch's where those assertions
// are evaluated and the result is pushed to an array - this string will be inlined into the program
// that the vm will run
const assertionString = assertions
    .map(a =>  // put assertion into a try-catch
    `
        ran = {id: ${a.id}, assertion: '${a.assertion}', is_public: ${a.is_public}}
        try {
            ${a.assertion} // run the assertion
            ran.passed = true
        } catch(e) {
            ran.passed = false
            ran.error = stringifyError(e)
        }
        output.push(ran)
    `)
    .reduce((a,b) => a+b, "") // reduce array of strings to a string


// support for executing the user-submitted program
// contains a utility function to stringify errors, the user code, and a series of try-catch's
// where assertions are ran against the user code; the program evaluates to an array of outcomes
// resulting from those assertions
const runnableProgram = `
// utility function to turn Error data to strings
function stringifyError(err, filter, space) {
    var plainObject = {};
    Object.getOwnPropertyNames(err).forEach(function(key) {
      plainObject[key] = err[key]
    })
    return JSON.stringify(plainObject, filter, space)
}
const assert = require("assert")
const output = [] // collect output from running assertions on user program


// USER CODE BEGINS HERE

${userCode}

// USER CODE ENDS HERE

// inline assertions

${assertionString}

output`

//console.log(runnableProgram)

try {
    output = safevm.run(runnableProgram) // run program
    console.log(JSON.stringify({ tests: output})) // output outcome so Django can collect it
} catch(e) {
    console.log(JSON.stringify(
        {
            error: stringifyError(e)
        }
    ))
}

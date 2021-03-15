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
const {VM} = require('vm2');
const assert = require("assert")
const AssertionError = require('assert').AssertionError;


// instantiation of the vm that'll run the user-submitted program
const safevm = new VM({
    timeout: 1000, // set timeout to 1000ms to prevent endless loops from running forever
    sandbox: {
        prettyPrintError,
        prettyPrintAssertionError,
        assert,
        AssertionError,
    }
})


// extracts useful information from vm error messages, throwing away all the data about vm context
// which is irrelevant to the user-submitted program
function prettyPrintError(e) {
    const [errMsg, errStackLine] = e.stack.split("\n")
    // get line and char position information
    // the -1 offset on line number is because the code ran by the vm adds a `const output = []` on the
    // first line before injecting user's code
    const errStackLineFormatted = 
        errStackLine
        .replace(/(.*):(\d+):(\d+)/g, 
            function(a,b,c,d) {
                return `on line ${parseInt(c)-1}, at position ${d}` 
            }
        )
    return errMsg +
          (
              errMsg.match(/Script execution timed out after/g) ? 
              "" : // hide line information if error is about the code timing out
              (" " + errStackLineFormatted)
          )
}

// does the same as prettyPrintError(), but it's specifically designed to work with AssertionErrors
function prettyPrintAssertionError(e) {
    const expected = e.expected
    const actual = e.actual
    const [ errMsg, _ ] = e.stack.split("\n")
    return errMsg + " expected value " + JSON.stringify(expected) + ", but got " + JSON.stringify(actual)
}

const userCode = process.argv[2]

const assertions = JSON.parse(process.argv[3])

// [
//     {
//         id: 1,
//         assertion: 'assert.strictEqual(max(1,2),2)',
//         public: true,
//     },    
//     {
//         id: 2,
//         assertion: 'assert.strictEqual(max(22,10),22)',
//         public: true,
//     },    
//     {
//         id: 3,
//         assertion: 'assert.strictEqual(max(-1,0),0)',
//         public: false,
//     },
// ]

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
            if(e instanceof AssertionError) {
                ran.error = prettyPrintAssertionError(e)
            } else {
                ran.error = prettyPrintError(e)
            }
        }
        output_wquewoajfjoiwqi.push(ran)
    `)
    .reduce((a,b) => a+b, "") // reduce array of strings to a string


// support for executing the user-submitted program
// contains a utility function to stringify errors, the user code, and a series of try-catch's
// where assertions are ran against the user code; the program evaluates to an array of outcomes
// resulting from those assertions
const runnableProgram = `const output_wquewoajfjoiwqi = []; const arr_jiodferwqjefio = Array; const push_djiowqufewio = Array.prototype.push; const shift_dfehwioioefn = Array.prototype.shift
${userCode}
// USER CODE ENDS HERE

// restore array prototype and relevant array methods in case user tampered with them
Array = arr_jiodferwqjefio
Array.prototype.push = push_djiowqufewio;
Array.prototype.shift = shift_dfehwioioefn;

if(Object.isFrozen(output_wquewoajfjoiwqi)) {
    // abort if user intentionally froze the output array
    throw new Error("Malicious user code froze vm's output array")
}

while(output_wquewoajfjoiwqi.length) {
    output_wquewoajfjoiwqi.shift() // make sure the output array is empty
}

// inline assertions

${assertionString}

// output outcome object to console
output_wquewoajfjoiwqi`


try {
    const outcome = safevm.run(runnableProgram) // run program
    console.log(JSON.stringify({ tests: outcome})) // output outcome so Django can collect it
} catch(e) {
    console.log(JSON.stringify({ error: prettyPrintError(e) }))
}


/*
this stuff is no longer needed and is to be removed soon

const { string } = require('yargs');


// utility function to turn Error data to strings
function stringifyError(err, filter, space) {
    var plainObject = {};
    Object.getOwnPropertyNames(err).forEach(function(key) {
      plainObject[key] = err[key]
    })
    return JSON.stringify(plainObject, filter, space)
}
*/

/*
usage: 
node runWithAssertions.js programCode assertions
arguments:
programCode is a STRING containing a js program
assertions is an ARRAY of strings representing assertions made using node assertions
useJs? (default false)

output: 
an array printed to the console (and collected by Django via subprocess.check_output()) where each
entry corresponds to an assertion and is an object:
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

// The VM2 module allows execution of arbitrary code safely using
// a sandboxed, secure virtual machine
const { VM } = require("vm2");
const assert = require("assert");
const AssertionError = require("assert").AssertionError;
const timeout = 1000;
const compileTsToJs = require("./tsCompilation").tsToJs;
const utils = require("./utils");

// rename assert and AssertionError inside generated program to make them inaccessible to user
const assertIdentifier = utils.getRandomIdentifier(20);
const assertionErrorIdentifier = utils.getRandomIdentifier(20);

// instantiation of the vm that'll run the user-submitted program
const safeVm = new VM({
  timeout, // set timeout to prevent endless loops from running forever
  sandbox: {
    prettyPrintError: utils.prettyPrintError,
    prettyPrintAssertionError: utils.prettyPrintAssertionError,
    [assertIdentifier]: assert,
    [assertionErrorIdentifier]: AssertionError,
  },
});

const useJs = JSON.parse(process.argv[4] ?? "false");

let userCode;

if (useJs) {
  userCode = process.argv[2];
} else {
  const compilationResult = compileTsToJs(process.argv[2]);
  if (compilationResult.compilationErrors.length > 0) {
    console.log(
      JSON.stringify({
        compilation_errors: compilationResult.compilationErrors,
      })
    );
    process.exit(0);
  }
  userCode = compilationResult.compiledCode;
}

const assertions = JSON.parse(process.argv[3]);

const outputArrIdentifier = utils.getRandomIdentifier(32);
const testDetailsObjIdentifier = utils.getRandomIdentifier(32);

// turn array of strings representing assertions to a series of try-catch blocks
//  where those assertions are evaluated and the result is pushed to an array
// the resulting string will be inlined into the program that the vm will run
const assertionString = assertions
  .map(
    (a) =>
      `
      ${testDetailsObjIdentifier} = {id: ${
        a.id
      }, assertion: \`${utils.escapeBackTicks(a.assertion)}\`, is_public: ${
        a.is_public
      }}
        try {
            ${a.assertion.replace(
              "assert",
              assertIdentifier
            )} // run the assertion
            ${testDetailsObjIdentifier}.passed = true // if no exception is thrown, the test case passed
        } catch(e) {
            ${testDetailsObjIdentifier}.passed = false
            if(e instanceof ${assertionErrorIdentifier}) {
                ${testDetailsObjIdentifier}.error = prettyPrintAssertionError(e)
            } else {
                ${testDetailsObjIdentifier}.error = prettyPrintError(e)
            }
        }
        ${outputArrIdentifier}[${outputArrIdentifier}.length] = ${testDetailsObjIdentifier} // push test case results
    `
  )
  .reduce((a, b) => a + b, ""); // reduce array of strings to a string

const runnableProgram = `const ${outputArrIdentifier} = [];
${userCode}
// USER CODE ENDS HERE
if(Object.isFrozen(${outputArrIdentifier})) {
    // abort if user intentionally froze the output array
    throw new Error("Internal error")
}
// inline assertions
${assertionString}
// output outcome object to console
${outputArrIdentifier}`;

try {
  const outcome = safeVm.run(runnableProgram); // run program
  //console.log(JSON.stringify({ error: runnableProgram })); -- for debugging, to get the generated program
  console.log(JSON.stringify({ tests: outcome })); // output outcome so Django can collect it
} catch (e) {
  // an error occurred before any test cases could be ran
  console.log(JSON.stringify({ error: utils.prettyPrintError(e) }));
}

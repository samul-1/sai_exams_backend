//import * as ts from "typescript";
const ts = require("typescript");
const tsConfig = require("./tsconfig.json");

const source = `
const max = (a: number, b:number):number => dfa>b?a:"werfgef";
max("asjdi", 1)`;

let result = ts.transpileModule(
  source,
  tsConfig
  // {
  //   compilerOptions: { module: ts.ModuleKind.CommonJS },
  // }
);

console.log(JSON.stringify(result));

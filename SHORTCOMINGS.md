# Mathpub System Shortcomings

This document details the issues, missing features, and friction points identified in the `mathpub` system during the drafting and compilation of Chapter 8 ("Polynomials and Factoring").

## 1. Rigid Example Component Schema
For components of `kind = "example"`, the schema (`src/mathpub/schemas/component-v1.json`) requires all of the following fragment keys:
* `prompt`
* `thought_process`
* `steps`
* `result`

This forces authors to split even static, simple examples into multiple `.tex` files or register empty placeholders (e.g. `steps = "steps.tex"` pointing to an empty file) instead of allowing a single cohesive `body.tex` fragment.

## 2. Plural Directory Names vs. Singular Kinds
The standard component directory structure uses plural names for several sub-blocks (e.g., `objectives/`, `misconceptions/`, `teaching-tips/`). However, the metadata schema requires singular values for the `kind` field (`"objective"`, `"misconception"`, `"teaching-tip"`). This mismatch creates naming inconsistencies and validation errors during authoring.

## 3. Math Mode Vulnerabilities in Answer Keys
In the answer key projection, raw answer texts are passed directly to `\annaanswer{...}`. If the author forgets to enclose equations or negative signs in math delimiters (`$`), `pdflatex` fails with obscure errors. The compiler should automatically wrap mathematical outputs in inline math blocks or validate syntax beforehand to prevent TeX crashes.

## 4. TeX Error Diagnostics are Buried
When TeX compilation fails, the CLI output only points to a build log inside a temporary directory (e.g., `build/algebra1.chapter8-components/failed-3grpx_xj/algebra1.chapter8-components-original-answers.build.log`). The developer must manually locate and parse this log file to find the failing line or package error. The mathpub runner should parse and surface the specific TeX error line/context directly to the CLI output.

## 5. Preview Command Limitations
The `preview` command only resolves questions that are located in `question_roots` (configured via `question.toml` files). It raises an error for questions modeled as components inside `component_roots` (configured via `component.toml` with `kind = "question"`). Standalone previewing of component-based questions is therefore unsupported; they can only be previewed by compiling the entire publication.

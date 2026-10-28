"""
web_server.py - Interactive Web Compiler Application for User-Defined Expressions.

Built for live academic evaluation:
- Accepts ANY user-defined infix mathematical expression entered in real time.
- Automatically detects user-defined variables (e.g. x, alpha, var1) and generates live input fields.
- Step-by-step compiler pipeline:
    1. Lexical Analysis & Token Stream
    2. Dijkstra's Shunting-Yard Algorithm with Step-by-Step Trace Player
    3. Live Interactive SVG Abstract Syntax Tree (AST) Visualization
    4. Dual-Parser Equivalence Check (Postfix Stack AST vs Recursive Descent AST)
    5. Tree Traversals (Inorder parenthesized, Preorder prefix, Postorder postfix)
    6. Dynamic Environment Evaluator with User-Defined Variable Values
    7. Diagnostic Error Detection with Caret Pointers

Usage:
  python web_server.py
  (Automatically opens http://localhost:8000 in your browser)
"""

import http.server
import json
import os
import socketserver
import sys
import webbrowser
from typing import Any, Dict, List, Optional, Union

# Ensure current directory is on Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from lexer import LexerError, Token, TokenType, tokenize
from infix_to_postfix import (
    ShuntingYardError,
    format_trace_table,
    infix_to_postfix,
    postfix_to_string,
)
from ast_builder import (
    ASTBuildError,
    ASTNode,
    BinaryOpNode,
    NumberNode,
    UnaryOpNode,
    VariableNode,
    build_ast_from_infix,
    build_ast_from_postfix,
)
from tree_ops import (
    EvaluationError,
    collect_variables,
    evaluate,
    inorder,
    postorder_str,
    preorder_str,
    tree_to_ascii,
)


def ast_to_dict(node: ASTNode) -> Dict[str, Any]:
    """Serializes AST to a nested dictionary for SVG diagram rendering."""
    if isinstance(node, NumberNode):
        return {
            "type": "NumberNode",
            "label": str(node.value),
            "category": "number",
            "value": node.value,
        }
    if isinstance(node, VariableNode):
        return {
            "type": "VariableNode",
            "label": node.name,
            "category": "variable",
            "name": node.name,
        }
    if isinstance(node, UnaryOpNode):
        return {
            "type": "UnaryOpNode",
            "label": f"u{node.op}",
            "op": node.op,
            "category": "unary",
            "children": [
                {"role": "operand", **ast_to_dict(node.operand)}
            ],
        }
    if isinstance(node, BinaryOpNode):
        return {
            "type": "BinaryOpNode",
            "label": node.op,
            "op": node.op,
            "category": "binary",
            "children": [
                {"role": "L", **ast_to_dict(node.left)},
                {"role": "R", **ast_to_dict(node.right)},
            ],
        }
    return {"type": "Unknown", "label": str(node), "category": "unknown"}


def compile_user_expression(expr: str, vars_dict: Optional[Dict[str, Union[int, float]]] = None) -> Dict[str, Any]:
    """Compiles any arbitrary user-defined expression and returns full compiler stages."""
    if vars_dict is None:
        vars_dict = {}

    response: Dict[str, Any] = {
        "success": False,
        "expression": expr,
        "tokens": [],
        "trace": [],
        "postfix": "",
        "ast_verification": {},
        "ast_ascii": "",
        "ast_tree": None,
        "traversals": {},
        "evaluation": {},
        "detected_variables": [],
        "error": None,
    }

    if not expr or not expr.strip():
        response["error"] = {"phase": "Input Validation", "message": "Please enter an arithmetic expression."}
        return response

    # 1. Lexical Analysis
    try:
        tokens = tokenize(expr)
        response["tokens"] = [
            {
                "type": t.type.name,
                "value": str(t.value),
                "line": t.line,
                "column": t.column,
            }
            for t in tokens
            if t.type != TokenType.EOF
        ]
        # Detect all identifier names from token stream
        response["detected_variables"] = sorted(list({
            t.value for t in tokens if t.type == TokenType.IDENTIFIER
        }))
    except LexerError as e:
        response["error"] = {"phase": "Lexical Analysis (Scanner)", "message": str(e)}
        return response

    # 2. Syntactic Analysis (Shunting-Yard)
    try:
        postfix_tokens, trace = infix_to_postfix(tokens)
        response["postfix"] = postfix_to_string(postfix_tokens)
        response["trace"] = [
            {"token": step.token, "stack": step.stack, "output": step.output}
            for step in trace
        ]
    except ShuntingYardError as e:
        response["error"] = {"phase": "Syntactic Analysis (Shunting-Yard)", "message": str(e)}
        return response

    # 3. Dual AST Construction & Verification
    try:
        ast_post = build_ast_from_postfix(postfix_tokens)
        ast_infix = build_ast_from_infix(tokens)
        is_match = (ast_post == ast_infix)

        response["ast_verification"] = {
            "match": is_match,
            "postfix_ast": repr(ast_post),
            "infix_ast": repr(ast_infix),
        }
        response["ast_tree"] = ast_to_dict(ast_post)
        response["ast_ascii"] = tree_to_ascii(ast_post, use_unicode=True)
    except ASTBuildError as e:
        response["error"] = {"phase": "AST Construction", "message": str(e)}
        return response

    # 4. Tree Traversals
    response["traversals"] = {
        "inorder": inorder(ast_post),
        "preorder": preorder_str(ast_post),
        "postorder": postorder_str(ast_post),
    }

    # 5. Semantic Evaluation
    needed_vars = sorted(list(collect_variables(ast_post)))
    response["detected_variables"] = needed_vars

    try:
        eval_result = evaluate(ast_post, vars_dict)
        response["evaluation"] = {
            "result": eval_result,
            "environment": {k: vars_dict[k] for k in needed_vars if k in vars_dict},
            "error": None,
        }
        response["success"] = True
    except EvaluationError as e:
        response["evaluation"] = {
            "result": None,
            "environment": vars_dict,
            "error": str(e),
        }
        response["success"] = True

    return response


# Modern user-input-first single-page application
HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Compiler Construction | User-Defined Expression Analyzer</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0b1120;
      --card-bg: #1e293b;
      --card-border: #334155;
      --primary: #38bdf8;
      --primary-hover: #0284c7;
      --accent-purple: #c084fc;
      --accent-green: #34d399;
      --accent-red: #f87171;
      --accent-amber: #fbbf24;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg-dark);
      color: var(--text-main);
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      line-height: 1.5;
      padding: 24px;
    }
    .container {
      max-width: 1280px;
      margin: 0 auto;
    }
    header {
      background: linear-gradient(135deg, #1e293b 0%, #0b1120 100%);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 24px 32px;
      margin-bottom: 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
    }
    .header-title h1 {
      font-size: 1.6rem;
      font-weight: 700;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .badge-live {
      background: rgba(56, 189, 248, 0.15);
      color: var(--primary);
      border: 1px solid rgba(56, 189, 248, 0.4);
      font-size: 0.75rem;
      padding: 4px 10px;
      border-radius: 9999px;
      font-weight: 600;
    }
    .header-title p {
      color: var(--text-muted);
      font-size: 0.9rem;
      margin-top: 4px;
    }

    /* Main User Input Console */
    .input-console {
      background: var(--card-bg);
      border: 2px solid #38bdf8;
      border-radius: 16px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 0 25px rgba(56, 189, 248, 0.15);
    }
    .console-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .console-header label {
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--primary);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .hint-text {
      font-size: 0.8rem;
      color: var(--text-muted);
    }
    .main-input-wrapper {
      display: flex;
      gap: 12px;
      margin-bottom: 16px;
    }
    .expr-input {
      flex: 1;
      background: #0b1120;
      border: 1px solid var(--card-border);
      color: #fff;
      font-family: 'Fira Code', monospace;
      font-size: 1.25rem;
      padding: 14px 20px;
      border-radius: 12px;
      outline: none;
      transition: all 0.2s ease;
    }
    .expr-input:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.25);
    }
    .btn-compile {
      background: linear-gradient(135deg, var(--primary) 0%, #6366f1 100%);
      color: #0b1120;
      border: none;
      padding: 0 32px;
      border-radius: 12px;
      font-weight: 700;
      font-size: 1.05rem;
      cursor: pointer;
      transition: all 0.2s;
      white-space: nowrap;
    }
    .btn-compile:hover {
      opacity: 0.95;
      transform: translateY(-1px);
      box-shadow: 0 4px 15px rgba(56, 189, 248, 0.4);
    }

    /* Dynamic User Variables Panel */
    .vars-panel {
      background: #0b1120;
      border: 1px dashed var(--card-border);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 16px;
    }
    .vars-panel-title {
      font-size: 0.82rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .vars-inputs-row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }
    .var-field {
      background: #1e293b;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 6px 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .var-name {
      font-family: 'Fira Code', monospace;
      font-weight: 600;
      color: var(--accent-amber);
      font-size: 0.95rem;
    }
    .var-input {
      background: #0b1120;
      border: 1px solid var(--card-border);
      color: #fff;
      font-family: 'Fira Code', monospace;
      font-size: 0.95rem;
      padding: 4px 8px;
      border-radius: 6px;
      width: 80px;
      outline: none;
    }
    .var-input:focus {
      border-color: var(--accent-amber);
    }

    /* Optional Samples Dropdown */
    .samples-toggle {
      font-size: 0.8rem;
      color: var(--text-muted);
      cursor: pointer;
      text-decoration: underline;
      display: inline-block;
      margin-top: 4px;
    }
    .samples-tray {
      display: none;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--card-border);
      gap: 8px;
      flex-wrap: wrap;
    }
    .sample-pill {
      background: #0b1120;
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      font-family: 'Fira Code', monospace;
      font-size: 0.8rem;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
    }
    .sample-pill:hover {
      background: #1e293b;
      color: var(--primary);
      border-color: var(--primary);
    }

    /* Verification Badge */
    .verification-banner {
      background: rgba(52, 211, 153, 0.12);
      border: 1px solid rgba(52, 211, 153, 0.35);
      color: var(--accent-green);
      padding: 14px 20px;
      border-radius: 12px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 600;
      font-size: 0.95rem;
    }
    .verification-banner.error {
      background: rgba(248, 113, 113, 0.12);
      border-color: rgba(248, 113, 113, 0.4);
      color: var(--accent-red);
    }

    /* Grid Layout for Compiler Phases */
    .dashboard-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
      margin-bottom: 24px;
    }
    @media (max-width: 992px) {
      .dashboard-grid {
        grid-template-columns: 1fr;
      }
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      display: flex;
      flex-direction: column;
    }
    .card-title {
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--text-main);
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .phase-badge {
      font-size: 0.72rem;
      padding: 2px 8px;
      border-radius: 6px;
      background: #0b1120;
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      font-weight: 600;
      font-family: 'Fira Code', monospace;
    }

    /* Token Chips */
    .tokens-container {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }
    .token-chip {
      background: #0b1120;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 6px 10px;
      font-family: 'Fira Code', monospace;
      font-size: 0.85rem;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .token-chip.NUMBER { border-color: #059669; color: var(--accent-green); }
    .token-chip.OPERATOR { border-color: #0284c7; color: var(--primary); }
    .token-chip.UNARY_MINUS { border-color: #9333ea; color: var(--accent-purple); font-weight: 600; }
    .token-chip.IDENTIFIER { border-color: #d97706; color: var(--accent-amber); }
    .token-chip.LPAREN, .token-chip.RPAREN { border-color: #475569; color: var(--text-muted); }
    .token-type {
      font-size: 0.65rem;
      opacity: 0.7;
      text-transform: uppercase;
    }

    /* Shunting-Yard Trace Controls */
    .trace-controls {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    .trace-btn {
      background: #0b1120;
      color: var(--text-main);
      border: 1px solid var(--card-border);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.8rem;
      cursor: pointer;
    }
    .trace-btn:hover { background: var(--card-border); }
    .step-indicator {
      font-family: 'Fira Code', monospace;
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-left: auto;
    }
    .table-container {
      max-height: 280px;
      overflow-y: auto;
      border: 1px solid var(--card-border);
      border-radius: 8px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-family: 'Fira Code', monospace;
      font-size: 0.85rem;
      text-align: left;
    }
    th, td {
      padding: 10px 14px;
      border-bottom: 1px solid var(--card-border);
    }
    th {
      background: #0b1120;
      color: var(--text-muted);
      font-size: 0.75rem;
      text-transform: uppercase;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    tr.active-step {
      background: rgba(56, 189, 248, 0.15);
      border-left: 3px solid var(--primary);
    }

    /* Interactive SVG AST Tree */
    .ast-wrapper {
      width: 100%;
      height: 380px;
      background: #0b1120;
      border: 1px solid var(--card-border);
      border-radius: 12px;
      overflow: auto;
      display: flex;
      justify-content: center;
      align-items: center;
    }
    svg.ast-svg {
      width: 100%;
      height: 100%;
      min-width: 500px;
      min-height: 350px;
    }

    /* Traversals & Evaluation */
    .traversal-box {
      margin-bottom: 14px;
    }
    .traversal-title {
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      color: var(--text-muted);
      margin-bottom: 4px;
    }
    .code-pill {
      background: #0b1120;
      border: 1px solid var(--card-border);
      padding: 8px 12px;
      border-radius: 8px;
      font-family: 'Fira Code', monospace;
      font-size: 0.92rem;
      color: var(--primary);
      word-break: break-all;
    }

    .eval-highlight {
      background: linear-gradient(135deg, rgba(56, 189, 248, 0.1) 0%, rgba(99, 102, 241, 0.1) 100%);
      border: 1px solid rgba(56, 189, 248, 0.3);
      padding: 16px;
      border-radius: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: auto;
    }
    .eval-val {
      font-family: 'Fira Code', monospace;
      font-size: 2rem;
      font-weight: 700;
      color: var(--accent-green);
    }

    /* ASCII Tree Tab */
    .ascii-pre {
      background: #0b1120;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 14px;
      font-family: 'Fira Code', monospace;
      font-size: 0.85rem;
      color: #cbd5e1;
      max-height: 380px;
      overflow: auto;
      white-space: pre;
    }

    /* Error Message Box */
    .error-box {
      background: rgba(248, 113, 113, 0.1);
      border: 1px solid rgba(248, 113, 113, 0.4);
      color: #fca5a5;
      padding: 18px;
      border-radius: 12px;
      font-family: 'Fira Code', monospace;
      font-size: 0.9rem;
      white-space: pre-wrap;
      margin-bottom: 24px;
    }

    footer {
      text-align: center;
      color: var(--text-muted);
      font-size: 0.82rem;
      margin-top: 32px;
      padding: 16px;
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <header>
      <div class="header-title">
        <h1>Compiler Construction Visualizer <span class="badge-live">Live Interactive Demo</span></h1>
        <p>Infix to Postfix Converter (Shunting-Yard) &amp; Dual Abstract Syntax Tree (AST) Builder</p>
      </div>
      <div style="font-family: 'Fira Code', monospace; font-size: 0.8rem; color: var(--text-muted);">
        [Full Dynamic User-Defined Grammar &amp; Interpretation]
      </div>
    </header>

    <!-- Main User Input Console -->
    <div class="input-console">
      <div class="console-header">
        <label for="exprInput">
          <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
          Enter Any Custom Infix Expression:
        </label>
        <span class="hint-text">Press <strong>Enter</strong> to compile in real time</span>
      </div>

      <div class="main-input-wrapper">
        <input
          type="text"
          id="exprInput"
          class="expr-input"
          placeholder="e.g. (x + 5) * (y - 2) ^ 3"
          value="(x + 5) * (y - 2) ^ 3"
          autofocus
        >
        <button id="compileBtn" class="btn-compile" onclick="runCompile()">Compile &amp; Evaluate</button>
      </div>

      <!-- Live Dynamic Variable Environment Panel -->
      <div id="varsPanel" class="vars-panel">
        <div class="vars-panel-title">
          <span>Detected Variables in Expression:</span>
          <span style="font-size: 0.75rem; text-transform: none; color: var(--primary);">Automatically generated input fields for your variables</span>
        </div>
        <div id="varsInputsRow" class="vars-inputs-row">
          <span style="color: var(--text-muted); font-size: 0.85rem;">No variables detected yet.</span>
        </div>
      </div>

      <div>
        <span class="samples-toggle" onclick="toggleSamples()">Need inspiration? Show test patterns &darr;</span>
        <div id="samplesTray" class="samples-tray">
          <span class="sample-pill" onclick="loadSample('2 + 3 * 4', {})">2 + 3 * 4</span>
          <span class="sample-pill" onclick="loadSample('2 ^ 3 ^ 2', {})">2 ^ 3 ^ 2 (Right Assoc)</span>
          <span class="sample-pill" onclick="loadSample('(8 - 3) * (10 - 2 - 1)', {})">(8 - 3) * (10 - 2 - 1)</span>
          <span class="sample-pill" onclick="loadSample('2 * -x + y ^ 2', {x: 3, y: 4})">2 * -x + y ^ 2</span>
          <span class="sample-pill" onclick="loadSample('((a + 2) * -b) / (c ^ 2 % 5)', {a: 3, b: 4, c: 3})">((a + 2) * -b) / (c ^ 2 % 5)</span>
          <span class="sample-pill" onclick="loadSample('2 + * 3', {})">2 + * 3 (Syntax Error)</span>
        </div>
      </div>
    </div>

    <!-- Error Box -->
    <div id="errorContainer" style="display: none;" class="error-box"></div>

    <!-- Verification Banner -->
    <div id="verifyBanner" class="verification-banner">
      <span>&#10003;</span>
      <span id="verifyText">Dual-Parser Verification: [MATCH] Stack-based Postfix AST is structurally identical to Recursive Descent Infix AST</span>
    </div>

    <!-- Compiler Pipeline Dashboard -->
    <div class="dashboard-grid">
      <!-- Card 1: Lexical Analysis -->
      <div class="card">
        <div class="card-title">
          <span>1. Lexical Analysis</span>
          <span class="phase-badge">Phase 1: Scanner</span>
        </div>
        <div id="tokensContainer" class="tokens-container"></div>
        <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: auto;">
          Contextual scanning differentiates binary subtraction from unary negation (<span style="color: #c084fc; font-weight: 600;">u-</span>).
        </div>
      </div>

      <!-- Card 2: Postfix & Traversals -->
      <div class="card">
        <div class="card-title">
          <span>2. Traversals &amp; Evaluation</span>
          <span class="phase-badge">Phase 4: Tree Walks</span>
        </div>
        <div class="traversal-box">
          <div class="traversal-title">Inorder (Fully Parenthesized):</div>
          <div id="inorderOut" class="code-pill"></div>
        </div>
        <div class="traversal-box">
          <div class="traversal-title">Preorder (Prefix / Polish):</div>
          <div id="preorderOut" class="code-pill"></div>
        </div>
        <div class="traversal-box">
          <div class="traversal-title">Postorder (Postfix / RPN):</div>
          <div id="postorderOut" class="code-pill"></div>
        </div>
        <div class="eval-highlight">
          <div>
            <div style="font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase;">Evaluated Result:</div>
            <div id="evalEnv" style="font-size: 0.85rem; color: var(--text-main); font-family: 'Fira Code', monospace;"></div>
          </div>
          <div id="evalValue" class="eval-val">-</div>
        </div>
      </div>
    </div>

    <!-- Full Width Grid: Shunting-Yard Trace & AST Visualizer -->
    <div class="dashboard-grid">
      <!-- Card 3: Shunting-Yard Trace Player -->
      <div class="card">
        <div class="card-title">
          <span>3. Shunting-Yard Execution Trace</span>
          <span class="phase-badge">Phase 2: RPN Conversion</span>
        </div>
        <div class="trace-controls">
          <button class="trace-btn" onclick="prevStep()">&laquo; Prev</button>
          <button id="playBtn" class="trace-btn" onclick="togglePlay()">Play &#9654;</button>
          <button class="trace-btn" onclick="nextStep()">Next &raquo;</button>
          <button class="trace-btn" onclick="resetTrace()">Reset</button>
          <span id="stepCounter" class="step-indicator">Step 0 / 0</span>
        </div>
        <div class="table-container">
          <table id="traceTable">
            <thead>
              <tr>
                <th>Token</th>
                <th>Operator Stack</th>
                <th>Postfix Output</th>
              </tr>
            </thead>
            <tbody id="traceTbody"></tbody>
          </table>
        </div>
      </div>

      <!-- Card 4: Interactive SVG AST Diagram -->
      <div class="card">
        <div class="card-title">
          <span>4. Abstract Syntax Tree (AST) Visualizer</span>
          <span class="phase-badge">Phase 3: Visual IR</span>
        </div>
        <div class="ast-wrapper" id="astSvgWrapper">
          <svg id="astSvg" class="ast-svg"></svg>
        </div>
      </div>
    </div>

    <!-- ASCII Tree Card -->
    <div class="card" style="margin-bottom: 24px;">
      <div class="card-title">
        <span>5. Terminal ASCII Tree Hierarchy</span>
        <span class="phase-badge">Terminal Diagnostic Format</span>
      </div>
      <pre id="asciiTreePre" class="ascii-pre"></pre>
    </div>

    <footer>
      Compiler Construction Mini-Project | Live Arbitrary Expression Visualizer | Python 3 Standard Library
    </footer>
  </div>

  <script>
    let currentTrace = [];
    let currentStepIndex = 0;
    let playInterval = null;
    let userVariables = { x: 4, y: 1 }; // Default initial variable bindings

    function toggleSamples() {
      const tray = document.getElementById('samplesTray');
      tray.style.display = tray.style.display === 'flex' ? 'none' : 'flex';
    }

    function loadSample(expr, vars) {
      document.getElementById('exprInput').value = expr;
      userVariables = { ...vars };
      runCompile();
    }

    // Auto-detect variable names directly as user types
    document.getElementById('exprInput').addEventListener('input', (e) => {
      syncVariableInputs();
    });

    document.getElementById('exprInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        runCompile();
      }
    });

    function extractIdentifiers(expr) {
      const tokens = expr.match(/[a-zA-Z_][a-zA-Z0-9_]*/g) || [];
      return Array.from(new Set(tokens)).sort();
    }

    function syncVariableInputs() {
      const expr = document.getElementById('exprInput').value;
      const detected = extractIdentifiers(expr);
      const container = document.getElementById('varsInputsRow');

      if (detected.length === 0) {
        container.innerHTML = '<span style="color: var(--text-muted); font-size: 0.85rem;">No variables detected in this expression. Constants only.</span>';
        return;
      }

      container.innerHTML = '';
      detected.forEach(varName => {
        if (!(varName in userVariables)) {
          userVariables[varName] = 1; // Default initial value
        }

        const field = document.createElement('div');
        field.className = 'var-field';
        field.innerHTML = `
          <span class="var-name">${varName}</span>
          <span style="color: var(--text-muted);">=</span>
          <input
            type="number"
            step="any"
            class="var-input"
            value="${userVariables[varName]}"
            data-var="${varName}"
            onchange="updateVarValue('${varName}', this.value)"
            oninput="updateVarValue('${varName}', this.value)"
          >
        `;
        container.appendChild(field);
      });
    }

    function updateVarValue(name, val) {
      const num = parseFloat(val);
      userVariables[name] = isNaN(num) ? 0 : num;
      runCompile();
    }

    async function runCompile() {
      const expr = document.getElementById('exprInput').value.trim();
      const errorBox = document.getElementById('errorContainer');
      errorBox.style.display = 'none';

      if (!expr) {
        errorBox.style.display = 'block';
        errorBox.textContent = '[Input Error] Please enter an arithmetic expression above.';
        return;
      }

      try {
        const res = await fetch('/api/compile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ expr, vars: userVariables })
        });
        const data = await res.json();

        if (data.error) {
          errorBox.style.display = 'block';
          errorBox.textContent = `[${data.error.phase} ERROR]\\n${data.error.message}`;
          document.getElementById('verifyBanner').style.display = 'none';
          return;
        }

        renderResults(data);
      } catch (err) {
        errorBox.style.display = 'block';
        errorBox.textContent = `Server Connection Error: ${err.message}`;
      }
    }

    function renderResults(data) {
      // 1. Verification Banner
      const verifyBanner = document.getElementById('verifyBanner');
      const verifyText = document.getElementById('verifyText');
      verifyBanner.style.display = 'flex';
      if (data.ast_verification.match) {
        verifyBanner.className = 'verification-banner';
        verifyText.textContent = 'Dual-Parser Verification: [MATCH] Stack-based Postfix AST is structurally identical to Recursive Descent Infix AST';
      } else {
        verifyBanner.className = 'verification-banner error';
        verifyText.textContent = 'Dual-Parser Verification: [MISMATCH] Trees differed';
      }

      // 2. Tokens
      const tokensContainer = document.getElementById('tokensContainer');
      tokensContainer.innerHTML = '';
      data.tokens.forEach(tok => {
        const chip = document.createElement('div');
        chip.className = `token-chip ${tok.type}`;
        chip.title = `Line ${tok.line}, Col ${tok.column}`;
        chip.innerHTML = `<span>${tok.value}</span><span class="token-type">${tok.type}</span>`;
        tokensContainer.appendChild(chip);
      });

      // 3. Traversals & Evaluation
      document.getElementById('inorderOut').textContent = data.traversals.inorder || '-';
      document.getElementById('preorderOut').textContent = data.traversals.preorder || '-';
      document.getElementById('postorderOut').textContent = data.traversals.postorder || '-';

      const evalVal = document.getElementById('evalValue');
      const evalEnv = document.getElementById('evalEnv');
      if (data.evaluation.error) {
        evalVal.textContent = 'Error';
        evalVal.style.color = 'var(--accent-red)';
        evalEnv.textContent = data.evaluation.error;
      } else {
        evalVal.textContent = data.evaluation.result !== null ? data.evaluation.result : '-';
        evalVal.style.color = 'var(--accent-green)';
        const envEntries = Object.entries(data.evaluation.environment || {});
        evalEnv.textContent = envEntries.length ? '{' + envEntries.map(([k, v]) => `${k}: ${v}`).join(', ') + '}' : 'No variables';
      }

      // 4. Trace Table
      currentTrace = data.trace || [];
      currentStepIndex = currentTrace.length - 1;
      renderTraceTable();

      // 5. ASCII Tree
      document.getElementById('asciiTreePre').textContent = data.ast_ascii || 'No AST generated';

      // 6. SVG AST Diagram
      if (data.ast_tree) {
        renderSvgTree(data.ast_tree);
      }
    }

    // -------------------------------------------------------------
    // Shunting-Yard Trace Controls
    // -------------------------------------------------------------
    function renderTraceTable() {
      const tbody = document.getElementById('traceTbody');
      tbody.innerHTML = '';
      currentTrace.forEach((step, idx) => {
        const tr = document.createElement('tr');
        if (idx === currentStepIndex) tr.className = 'active-step';
        tr.innerHTML = `<td><strong>${step.token}</strong></td><td>${step.stack}</td><td>${step.output}</td>`;
        tbody.appendChild(tr);
      });
      document.getElementById('stepCounter').textContent = `Step ${currentStepIndex + 1} / ${currentTrace.length}`;
    }

    function nextStep() {
      if (currentStepIndex < currentTrace.length - 1) {
        currentStepIndex++;
        renderTraceTable();
      } else {
        pauseTrace();
      }
    }

    function prevStep() {
      if (currentStepIndex > 0) {
        currentStepIndex--;
        renderTraceTable();
      }
    }

    function resetTrace() {
      pauseTrace();
      currentStepIndex = 0;
      renderTraceTable();
    }

    function togglePlay() {
      if (playInterval) {
        pauseTrace();
      } else {
        const btn = document.getElementById('playBtn');
        btn.innerHTML = 'Pause &#10074;&#10074;';
        if (currentStepIndex >= currentTrace.length - 1) currentStepIndex = 0;
        playInterval = setInterval(() => {
          if (currentStepIndex < currentTrace.length - 1) {
            nextStep();
          } else {
            pauseTrace();
          }
        }, 800);
      }
    }

    function pauseTrace() {
      if (playInterval) {
        clearInterval(playInterval);
        playInterval = null;
        document.getElementById('playBtn').innerHTML = 'Play &#9654;';
      }
    }

    // -------------------------------------------------------------
    // SVG AST Tree Renderer
    // -------------------------------------------------------------
    function renderSvgTree(rootNode) {
      const svg = document.getElementById('astSvg');
      svg.innerHTML = '';

      let maxDepth = 0;
      function computeDepth(node, depth) {
        if (depth > maxDepth) maxDepth = depth;
        if (node.children) {
          node.children.forEach(c => computeDepth(c, depth + 1));
        }
      }
      computeDepth(rootNode, 1);

      let leafIndex = 0;
      function assignCoordinates(node, depth) {
        if (!node.children || node.children.length === 0) {
          node.x = leafIndex * 90 + 60;
          leafIndex++;
        } else {
          node.children.forEach(c => assignCoordinates(c, depth + 1));
          const firstChild = node.children[0];
          const lastChild = node.children[node.children.length - 1];
          node.x = (firstChild.x + lastChild.x) / 2;
        }
        node.y = depth * 75 - 15;
      }
      assignCoordinates(rootNode, 1);

      const totalWidth = Math.max(leafIndex * 90 + 120, 500);
      const totalHeight = Math.max(maxDepth * 75 + 60, 340);
      svg.setAttribute('viewBox', `0 0 ${totalWidth} ${totalHeight}`);

      // Draw Edges
      function drawEdges(node) {
        if (node.children) {
          node.children.forEach(child => {
            const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            line.setAttribute('x1', node.x);
            line.setAttribute('y1', node.y);
            line.setAttribute('x2', child.x);
            line.setAttribute('y2', child.y);
            line.setAttribute('stroke', '#475569');
            line.setAttribute('stroke-width', '2');
            svg.appendChild(line);

            if (child.role && (child.role === 'L' || child.role === 'R')) {
              const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
              text.setAttribute('x', (node.x + child.x) / 2 + (child.role === 'L' ? -10 : 6));
              text.setAttribute('y', (node.y + child.y) / 2 - 4);
              text.setAttribute('fill', '#94a3b8');
              text.setAttribute('font-size', '11');
              text.setAttribute('font-family', 'Fira Code, monospace');
              text.textContent = child.role;
              svg.appendChild(text);
            }

            drawEdges(child);
          });
        }
      }
      drawEdges(rootNode);

      // Draw Nodes
      function drawNodes(node) {
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');

        if (node.category === 'binary' || node.category === 'unary') {
          const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', node.x);
          circle.setAttribute('cy', node.y);
          circle.setAttribute('r', '20');
          circle.setAttribute('fill', node.category === 'unary' ? '#7e22ce' : '#0369a1');
          circle.setAttribute('stroke', node.category === 'unary' ? '#c084fc' : '#38bdf8');
          circle.setAttribute('stroke-width', '2');
          g.appendChild(circle);

          const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          text.setAttribute('x', node.x);
          text.setAttribute('y', node.y + 5);
          text.setAttribute('text-anchor', 'middle');
          text.setAttribute('fill', '#f8fafc');
          text.setAttribute('font-weight', '700');
          text.setAttribute('font-family', 'Fira Code, monospace');
          text.setAttribute('font-size', '14');
          text.textContent = node.label;
          g.appendChild(text);
        } else {
          const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          rect.setAttribute('x', node.x - 24);
          rect.setAttribute('y', node.y - 18);
          rect.setAttribute('width', '48');
          rect.setAttribute('height', '36');
          rect.setAttribute('rx', '8');
          rect.setAttribute('fill', node.category === 'number' ? '#065f46' : '#92400e');
          rect.setAttribute('stroke', node.category === 'number' ? '#34d399' : '#fbbf24');
          rect.setAttribute('stroke-width', '2');
          g.appendChild(rect);

          const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          text.setAttribute('x', node.x);
          text.setAttribute('y', node.y + 5);
          text.setAttribute('text-anchor', 'middle');
          text.setAttribute('fill', '#f8fafc');
          text.setAttribute('font-weight', '600');
          text.setAttribute('font-family', 'Fira Code, monospace');
          text.setAttribute('font-size', '13');
          text.textContent = node.label;
          g.appendChild(text);
        }

        svg.appendChild(g);

        if (node.children) {
          node.children.forEach(c => drawNodes(c));
        }
      }
      drawNodes(rootNode);
    }

    window.onload = () => {
      syncVariableInputs();
      runCompile();
    };
  </script>
</body>
</html>
"""


class CompilerHTTPHandler(http.server.SimpleHTTPRequestHandler):
    """Custom HTTP handler serving the web demo UI and compiler API."""

    def do_GET(self) -> None:
        if self.path in ('/', '/index.html'):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path == '/api/compile':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            try:
                data = json.loads(body)
                expr = data.get('expr', '')
                vars_dict = data.get('vars', {})
                result = compile_user_expression(expr, vars_dict)
            except Exception as e:
                result = {"success": False, "error": {"phase": "Server Error", "message": str(e)}}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard HTTP request logs to keep terminal clean."""
        pass


def start_server(port: int = 8000) -> None:
    """Starts the HTTP server and opens the browser."""
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), CompilerHTTPHandler) as httpd:
        url = f"http://localhost:{port}"
        print("=" * 65)
        print("  COMPILER CONSTRUCTION: USER-DEFINED EXPRESSION ANALYZER")
        print("=" * 65)
        print(f"  [+] Web UI running at:  {url}")
        print("  [+] Accepts any user-defined expression in real time.")
        print("  [+] Press Ctrl+C in terminal to stop.")
        print("=" * 65)
        print("  Opening web browser...\n")
        try:
            webbrowser.open(url)
        except Exception:
            pass

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Shutting down server. Goodbye!")


if __name__ == "__main__":
    port_num = 8000
    if len(sys.argv) > 1:
        try:
            port_num = int(sys.argv[1])
        except ValueError:
            pass
    start_server(port_num)

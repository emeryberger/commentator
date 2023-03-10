import openai
import os
import sys
import ast
import logging

from typing import cast, Optional, List, Set, Union

logname = 'commentator.log'
logging.basicConfig(filename=logname, filemode='a', format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s', datefmt='%H:%M:%S', level=logging.INFO)
logging.info('Running commentator.')

def get_comments(programming_language: str, translate_text: str, the_code: str) -> Optional[openai.api_resources.Completion]:
    """
    Rewrite the following `programming_language` code by adding high-level explanatory comments, PEP 257 docstrings, 
    and PEP 484 style type annotations. Infer what each function does, using the names and computations as hints. 
    If there are existing comments or types, augment them rather than replacing them. If the existing comments are 
    inconsistent with the code, correct them. Every function argument and return value should be typed if possible. 
    Do not change any other code. 
    
    :param programming_language: a string representing the programming language associated with the code to be 
                                  commented
    :param translate_text: a string representing the text to be translated
    :param the_code: a string representing the code to be commented
    :return: an optional completion object
    """
    content = f"Rewrite the following {programming_language}code by adding high-level explanatory comments, " \
              f"PEP 257 docstrings, and PEP 484 style type annotations. Infer what each function does, using the " \
              f"names and computations as hints. If there are existing comments or types, augment them rather than " \
              f"replacing them. If the existing comments are inconsistent with the code, correct them. Every " \
              f"function argument and return value should be typed if possible. Do not change any other code. " \
              f"{translate_text} {the_code}"    
    try:
        completion = openai.ChatCompletion.create(model='gpt-3.5-turbo', messages=[{'role': 'system', 'content': 'You are a {programming_language}programming assistant who ONLY responds with blocks of code. You never respond with text. Just code, starting with ``` and ending with ```.'}, {'role': 'user', 'content': content}])
    except openai.error.AuthenticationError:
        print()
        print('You need an OpenAI key to use commentator. You can get a key here: https://openai.com/api/')
        print('Invoke commentator with the api-key argument or set the environment variable OPENAI_API_KEY.')
        import sys
        sys.exit(1)
    except openai.error.APIError:
        # Something went wrong server-side. Hopefully, it's transient and retries will work.
        return None

    return completion

def update_args(old_function_ast: Union[ast.FunctionDef, ast.AsyncFunctionDef], new_function_ast: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> Union[ast.FunctionDef, ast.AsyncFunctionDef]:
    """
    Updates the arguments of a function defined by `old_function_ast` with the arguments of `new_function_ast`.

    Args:
        old_function_ast: The AST node of the function to be updated.
        new_function_ast: The AST node of the function whose arguments to update with.

    Returns:
        The updated AST node of the old function.
    """
    arg_names = [arg.arg for arg in old_function_ast.args.args]
    new_args = []
    for arg in new_function_ast.args.args:
        if arg.arg in arg_names:
            old_arg = old_function_ast.args.args[arg_names.index(arg.arg)]
            new_arg = ast.arg(arg=arg.arg, annotation=arg.annotation)
            new_args.append(new_arg)
        else:
            new_args.append(arg)
    old_function_ast.args.args = new_args
    return old_function_ast
test = '\ndef abs(n):\n    """ WUT """\n    # Check if integer is negative\n    if n < 0:\n        # Return the opposite sign of n (i.e., multiply n by -1)\n        return -n\n    else:\n        # Return n (which is already a positive integer or zero)\n        return n\n'
test2 = '\ndef abs(n):\n    if n < 0:\n        return -n\n    else:\n        return n\n'
import ast

def remove_code_before_function(code: str) -> str:
    """
    Remove any code above a function definition in the provided code string.

    Args:
        code: The code string to process.

    Returns:
        The code string with all code above the first function definition removed.
    """
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start_index = node.lineno - 1
            break
    else:
        return code
    lines = code.splitlines()
    return '\n'.join(lines[start_index:])

def remove_annotations(node: ast.AST) -> None:
    """
    Removes type annotations from an Abstract Syntax Tree node if they exist, both for function and variable annotations.

    Args:
        node: The AST node to remove annotations from.
    """
    if isinstance(node, ast.AnnAssign):
        del node.annotation # FIXME?
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for arg in node.args.args:
            arg.annotation = None
        node.returns = None

def remove_comments(node: Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module, ast.Expr]) -> None:
    """
    Removes comments in a Python code node.
    :param node: The code node to remove comments from.
    """
    if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.ClassDef) or isinstance(node, ast.Module):
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Str):
            node.body[0].value.s = ''
        node.body = [n for n in node.body if not isinstance(n, ast.Expr) or not isinstance(n.value, ast.Str)]
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Str):
        node.value.s = ''

def compare_python_code(code1, code2):
    tree1 = ast.parse(code1)
    tree2 = ast.parse(code2)
    for node in ast.walk(tree1):
        remove_comments(node)
        remove_annotations(node)
    for node in ast.walk(tree2):
        remove_comments(node)
        remove_annotations(node)
    try:
        diff = ast.unparse(tree1) == ast.unparse(tree2)
        return diff
    except:
        return False

def has_types(func_code: str) -> bool:
    """
    Check if a given function has type annotations for all its arguments and return value.

    Args:
        func_code: The code of the function to check.

    Returns:
        True if the function has type annotations for all its arguments and its return value.
        False otherwise.

    """
    tree = ast.parse(func_code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_typed = all([arg.annotation is not None for arg in node.args.args]) and node.returns is not None
            return all_typed
    return False

def has_docstring(func_code: str) -> bool:
    """
    Determine if a given function has a docstring.

    Args:
        func_code (str): Function code in string form.

    Returns:
        bool: True if the function has a docstring, False otherwise.
    """
    tree = ast.parse(func_code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Str):
                return len(node.body[0].value.s) > 0
    return False

def now_has_types(code1, code2):
    tree1 = ast.parse(code1)
    tree2 = ast.parse(code2)
    for node in ast.walk(tree2):
        remove_annotations(node)
    return ast.unparse(tree1) != ast.unparse(tree2)

def extract_function_ast(program_str: str, function_name: str) -> Union[ast.FunctionDef, ast.AsyncFunctionDef]:
    """
    Extract the abstract syntax tree (AST) for a function with a given name from a given program string.

    Args:
        program_str (str): A string representing the program code.
        function_name (str): A string representing the name of the function to extract the AST for.

    Returns:
        ast.FunctionDef: The AST node representing the function definition.

    Raises:
        ValueError: If no function with the given name is found in the AST.
    """
    program_ast = ast.parse(program_str)
    function_node = next((n for n in program_ast.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function_name), None)
    if function_node is None:
        raise ValueError(f"No function named '{function_name}' was found")
    return function_node

def extract_function_source(program_str, function_name):
    return ast.unparse(extract_function_ast(program_str, function_name))
    program_ast = ast.parse(program_str)
    function_node = next((n for n in program_ast.body if isinstance(n, ast.FunctionDef) and n.name == function_name), None)
    if function_node is None:
        raise ValueError(f"No function named '{function_name}' was found")
    return ast.unparse(function_node)

def enumerate_functions(program_str: str) -> List[str]:
    """
    Returns a list of names of functions and async functions defined in a given Python program string.

    Args:
        program_str: A Python program in string format.

    Returns:
        A list of names of functions and async functions defined in the program.
    """
    program_ast = ast.parse(program_str)
    names = [n.name for n in program_ast.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return names

def replace_function(program_str: str, function_name: str, new_function_str: str) -> str:
    """Replace a function within a Python program with a new function.

    Args:
        program_str: A string representing a Python program.
        function_name: The name of the function to be replaced.
        new_function_str: A string representing the new function to replace the old one.

    Returns:
        A string representing the modified Python program.
    """
    program_ast = ast.parse(program_str)
    function_node = next((n for n in program_ast.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function_name), None)
    if function_node is None:
        raise ValueError(f"No function named '{function_name}' was found")
    new_function_ast = extract_function_ast(new_function_str, function_name)
    function_node.body = new_function_ast.body
    function_node.returns = new_function_ast.returns
    update_args(function_node, new_function_ast)
    return ast.unparse(program_ast)

def extract_names(ast_node: ast.AST) -> Set[str]:
    """
    Extracts all class, function, and variable names from a parsed AST node.

    Args:
        ast_node: A parsed Abstract Syntax Tree (AST) node.

    Returns:
        A set of all the found class, function, and variable names.
    """
    names = set()
    for child in ast.iter_child_nodes(ast_node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(child.name)
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        names.update(extract_names(child))
    return names

def get_language_from_file_name(file_name: str) -> str:
    """Given a file name, extracts the extension and maps it to a programming language.

    Args:
      file_name: A string representing the name of the file.

    Returns:
      A string representing a programming language, or an empty string if the extension is not recognized.
    """
    ext = file_name.split('.')[-1]
    language_map = {'js': 'JavaScript', 'ts': 'TypeScript', 'c': 'C', 'cpp': 'C++', 'cs': 'C#', 'swift': 'Swift', 'py': 'Python', 'rs': 'Rust', 'sql': 'SQL', 'css': 'CSS', 'php': 'PHP', 'rb': 'Ruby', 'kt': 'Kotlin', 'go': 'Go', 'r': 'R', 'java': 'Java', 'h': 'C', 'hpp': 'C++', 'hxx': 'C++'}
    if ext in language_map:
        return language_map[ext]
    else:
        return ''

def find_code_start(code):
    lines = code.split('\n')
    i = 0
    while i < len(lines) and lines[i].strip() == '':
        i += 1
    first_line = lines[i].strip()
    if first_line == '```':
        return 3
    if first_line.startswith('```'):
        word = first_line[3:].strip()
        if len(word) > 0 and ' ' not in word:
            return len(word) + 3
    return -1
test = '\n```python\ndef abs(n):\n    # Check if integer is negative\n    if n < 0:\n        # Return the opposite sign of n (i.e., multiply n by -1)\n        return -n\n    else:\n        # Return n (which is already a positive integer or zero)\n        return n\n```\n'

def commentate(filename, code, language=None):
    """
    This function takes in a string of code and an optional language parameter. If language is specified,
    the function translates each docstring and comment in the code to the specified language and includes the 
    translated text in the output. If language is not specified, the function does not include any translations
    in the output. The output text includes the original code, high-level explanatory comments, and any 
    translated text (if language is specified). 

    Args:
    code (str): A string of code.
    language (str, optional): A language code to specify the output language of docstrings and comments. 
                              Defaults to None.

    Returns:
    str: A string of the processed code.
    """
    if language:
        translate_text = f"Write each docstring and comment first in English, then add a newline and '---', and add the translation to {language}."
    else:
        translate_text = ''
    programming_language = get_language_from_file_name(filename) + ' '
    max_tries = 3
    for func_name in enumerate_functions(code):
        tries = 0
        while tries < max_tries:
            tries += 1
            print(f'  commentating {func_name} ({tries}) ...', end='', flush=True)
            the_code = extract_function_source(code, func_name)
            if has_docstring(the_code) and has_types(the_code):
                print('already has a docstring and types.')
                break

            completion = get_comments(programming_language, translate_text, the_code)
            
            c = completion
            text = c['choices'][0]['message']['content']
            first_index = find_code_start(text)
            second_index = text.find('```', first_index + 1)
            if first_index == -1 or second_index == -1:
                code_block = text
            else:
                code_block = text[first_index:second_index]
            if get_language_from_file_name(filename) == 'Python':
                try:
                    result_ast = ast.parse(code_block)
                except:
                    print('failed (parse failure).')
                    logging.error(f'Parse failure:\n{code_block}')
                    result_ast = None
            if result_ast:
                orig_ast = ast.parse(the_code)
                if not compare_python_code(remove_code_before_function(the_code), remove_code_before_function(code_block)):
                    print('failed (failed to validate).')
                    logging.error(f'Validation failure:\n{code_block}')
                    code_block = None
            else:
                code_block = None
            if code_block:
                if not has_types(code_block):
                    print('Failed to add types.')
                    logging.error(f'Failed to add types:\n{code_block}')
                else:
                    print(f'success!')
                    code = replace_function(code, func_name, code_block)
                    break
    return code

def api_key():
    key = ''
    try:
        key = os.environ['OPENAI_API_KEY']
    except:
        pass
    return key

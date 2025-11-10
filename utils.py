import re
import streamlit as st
import pandas as pd
import jinja2
from jinja2 import Environment, BaseLoader
import logging


def carregar_dados(filepath, sheet_name=0, skiprows=2):
    """Lê um arquivo Excel e retorna um DataFrame, tratando erros."""
    try:
        return pd.read_excel(filepath, sheet_name=sheet_name, skiprows=skiprows).map(lambda x: x.strip() if isinstance(x, str) else x)
    except Exception as e:
        st.error(f"Erro ao carregar a planilha '{sheet_name}': {e}")
        return None

def get_variaveis_template(template_md_content):
    """Coleta as variáveis presentes em um template Jinja2."""
    if not template_md_content:
        return set()
    env = Environment(loader=BaseLoader())
    ast = env.parse(template_md_content)
    return jinja2.meta.find_undeclared_variables(ast)

class StreamlitLogHandler(logging.Handler):
    """Handler de logging customizado para exibir logs do pypandoc no Streamlit."""
    def __init__(self, container):
        super().__init__()
        self.container = container
        self.records = []

    def emit(self, record):
        self.records.append(record)
        msg = self.format(record)
        self.container.warning(msg)


def parse_expression(expression):
    tokens = []
    current_token = ''

    for char in expression:
        if char in {'|', '&', '~', '(', ')'}:
            if current_token:
                tokens.append(current_token.strip())
                current_token = ''
            tokens.append(char)
        else:
            current_token += char

    if current_token:
        tokens.append(current_token.strip())

    return tokens

def infix_to_rpn(tokens):
    precedence = {'~': 3, '&': 2, '|': 1}
    output = []
    stack = []

    for token in tokens:
        if token == '(':
            # Abre parêntese
            stack.append(token)
        elif token == ')':
            # Fecha parêntese
            while stack and stack[-1] != '(':
                output.append(stack.pop())
            stack.pop()  # Remove o '('
        elif token in precedence:
            # Operador
            while stack and stack[-1] in precedence and precedence[stack[-1]] >= precedence[token]:
                output.append(stack.pop())
            stack.append(token)
        else:
            output.append(token)

    while stack:
        output.append(stack.pop())

    return list(filter(lambda x: x != '', output))

def avalia_expressao(expressao_achado, situacao_encontrada, debug=False):
    expressao_achado = str(expressao_achado)
    situacao_encontrada = str(situacao_encontrada)

    # Primeiro tenta se é o caso de um eval
    try:
        if debug:
            print(f"Testando se {situacao_encontrada} {expressao_achado} = {eval(f'{situacao_encontrada} {expressao_achado}')}")
        return eval(f'{situacao_encontrada} {expressao_achado}')
    except Exception as e:
        parsed_tokens = parse_expression(expressao_achado)
        tokens = infix_to_rpn(parsed_tokens)

        #print(tokens)

        pilha = []

        for token in tokens:
            if token == '|':
                # Operador OR
                y = pilha.pop()
                x = pilha.pop()
                pilha.append(x or y)
            elif token == '&':
                # Operador AND
                y = pilha.pop()
                x = pilha.pop()
                pilha.append(x and y)
            elif token == '~':
                x = pilha.pop()
                pilha.append(not x)
            else:
                # Aqui se remove o '.' no final da string pois não está padronizada as respostas.
                # Assim, encontra-se resposta terminando em '.' como 'Não adota' ou 'Não adota.'
                a = re.sub(r'\.$', '', token)
                b = re.sub(r'\.$', '', situacao_encontrada)
                if debug:
                    print(f"    Checa se {a} == {b} - ", a == b)
                pilha.append(a == b)

        if len(pilha) == 1:
            if debug:
                print('        Achado:', pilha[0])

            return pilha[0]
        else:
            raise ValueError("Expressão lógica inválida")

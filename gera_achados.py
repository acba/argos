#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import copy
import pickle
import pandas as pd
from docx import Document
import sys

from .utils import avalia_expressao
from .classes import FonteInformacao, Achado, AcaoVerificacao, ProcedimentoAuditoria, Auditado, \
    gerar_tabela_encaminhamentos, gerar_tabela_achados, gerar_tabela_situacoes_inconformes

pd.set_option('display.max_colwidth', None)

if not os.path.exists('resultado/relatorios'):
    os.makedirs('resultado/relatorios')

df_jurisdicionados   = pd.read_excel('../00-dados/bd_jurisdicionados.xlsx').applymap(lambda x: x.strip() if isinstance(x, str) else x)
df_procedimentos     = pd.read_excel('mapa-verificacao-achados.xlsx', sheet_name='Procedimentos de Auditoria', skiprows=2).applymap(lambda x: x.strip() if isinstance(x, str) else x)
df_acoes_verificacao = pd.read_excel('mapa-verificacao-achados.xlsx', sheet_name='Ações de Verificação', skiprows=2).applymap(lambda x: x.strip() if isinstance(x, str) else x)
df_fontes            = pd.read_excel('mapa-verificacao-achados.xlsx', sheet_name='Fontes de Informação', skiprows=2).applymap(lambda x: x.strip() if isinstance(x, str) else x)

# Leitura e criação dos objetos a partir das planilhas

# 1. Leitura das fontes de informação
fontes = {}
for _, row in df_fontes.iterrows():
    fonte = FonteInformacao(
        descricao=row['descricao'],
        filepath=row['filepath'],
        chave_jurisdicionado=row['chave_jurisdicionado'],
        id=row['id']
    )
    fontes[fonte.id] = fonte  # Armazena no dicionário para referência posterior

# 2. Leitura das ações de verificação
acoes = {}
for _, row in df_acoes_verificacao.iterrows():
    fonte_informacao = fontes.get(row['id_fonte_informacao'])

    acao = AcaoVerificacao(
        fonte_informacao=fonte_informacao,
        informacao_requerida=row['informacao_requerida'],

        acao_exclusiva_auditados=row['acao_exclusiva_auditados'],
        criterio=row['criterio'],
        descricao_situacao_inconforme=row['descricao_situacao_inconforme'],

        descricao_evidencia=row['descricao_evidencia'],
        situacao_inconforme=row['situacao_inconforme'],
        situacao_encontrada_nan_e_achado=row['situacao_encontrada_nan_e_achado'],
        tipo_encaminhamento=row['tipo_encaminhamento'],
        encaminhamento=row['encaminhamento'],
        pre_encaminhamento=row['pre_encaminhamento'],
        auditado_inexistente_e_achado=row['auditado_inexistente_e_achado'],
        descricao_auditado_inexistente=row['descricao_auditado_inexistente'],
        id=row['id']
    )
    acoes[acao.id] = acao  # Armazena no dicionário para referência posterior

# 3. Leitura dos procedimentos de auditoria
procedimentos = {}
for _, row in df_procedimentos.iterrows():
    procedimento = ProcedimentoAuditoria(
        descricao=row['descricao'],
        logica_achado=row['logica_achado'],
        numero_achado=row['numero_achado'],
        nome_achado=row['nome_achado'],
        id=row['id']
    )

    # Adiciona as ações de verificação relevantes que constam na lógica
    acao_ids = re.split(r'[\&\|\~\(\)\s]+', procedimento.logica_achado.replace("(", "").replace(")", ""))
    acao_ids = [acao_id for acao_id in acao_ids if acao_id]

    for acao_id in acao_ids:
        acao = acoes.get(acao_id.strip())
        if acao:
            procedimento.adicionar_acao(acao)
    procedimentos[procedimento.id] = procedimento

# 4. Leitura dos auditados
auditados = {}
for _, row in df_jurisdicionados.iterrows():
    auditado = Auditado(
        nome=row['orgao'],
        sigla=row['sigla'],
        # id=row['id']
    )
    auditados[auditado.sigla] = auditado

from IPython.display import Markdown

for auditado in auditados.values():
    print(f'Auditando {auditado.sigla}')
    auditado.aplicar_procedimentos(procedimentos.values(), debug=False)
    auditado.documenta_procedimentos()

    if auditado.tem_achados:
        for p in auditado.procedimentos_executados:
            if p.achado:
                print(f'Achado {p.achado.numero}: {p.achado.nome}')

        # display(Markdown(auditado.reporta_procedimentos()))
        # break
    else:
        print('Sem achados!')
    print()

    # display(Markdown(auditado.reporta_procedimentos()))
    # break


tabela_encaminhamentos = gerar_tabela_encaminhamentos(auditados, procedimentos)
tabela_encaminhamentos.T.to_excel('resultado/tabela_encaminhamentos_por_auditados.xlsx')

tabela_achados = gerar_tabela_achados(auditados, procedimentos)
tabela_achados.T.to_excel('resultado/tabela_achados_por_auditados.xlsx')

tabela_situacoes = gerar_tabela_situacoes_inconformes(auditados, procedimentos)
tabela_situacoes.T.to_excel('resultado/tabela_situacoes_inconformes_por_auditados.xlsx')

def gerar_tabela_acoesverificacao(auditados, procedimentos):
    # Coleta todos os encaminhamentos únicos
    todas_acoes = []
    for p in procedimentos.values():
        for acao in p.acoes_verificacao:
            # texto = f"[ACHADO {p.numero_achado}] {acao.informacao_requerida}"
            texto = f"[ACHADO {p.numero_achado}] {acao.informacao_requerida}"
            if texto not in todas_acoes:
                todas_acoes.append(texto)

    # Inicializa uma lista para armazenar os dados da tabela
    dados_tabela = []

    for auditado in auditados.values():
        if auditado.foi_auditado:
            acoes_info_auditado = []
            for p in auditado.procedimentos_executados:
                if p.achado is not None: # Se tem achado
                    for av in p.acoes_verificacao:
                        if av.resultado:
                            acoes_info_auditado.append(f"[ACHADO {p.numero_achado}] {av.informacao_requerida}")
                            # print(av)

            # print(acoes_info_auditado)

            linha = {f"{acaov}": ('X' if any([av == acaov for av in acoes_info_auditado]) else '') for acaov in todas_acoes}

            linha["Auditado"] = auditado.sigla  # Adiciona o identificador do auditado
            dados_tabela.append(linha)
        else:
            print(f'{auditado.sigla} ainda não foi auditado')


    # Cria o DataFrame com os dados coletados
    df_situacoes = pd.DataFrame(dados_tabela)
    df_situacoes = df_situacoes.set_index("Auditado")

    return df_situacoes


tbl_av = gerar_tabela_acoesverificacao(auditados, procedimentos)
tbl_av.T.to_excel('resultado/tabela_itens_por_auditado.xlsx')
tbl_av.head()

# Função para criar a expressão combinada
def criar_condicao(row):
    # Seleciona as colunas com 'X'
    entidades = row[row == 'X'].index.tolist()
    qtd_igual = len(entidades)
    qtd_diferente = len(row) - qtd_igual

    condicao = '=='
    if qtd_diferente < qtd_igual:
        condicao = '!='
        entidades = row[row != 'X'].index.tolist()

    # Cria a expressão OR
    if entidades:
        if condicao == '==':
            return ' OR '.join([f'TOKEN:FIRSTNAME == "{ent}"' for ent in entidades])
        else:
            return ' AND '.join([f'TOKEN:FIRSTNAME != "{ent}"' for ent in entidades])
    return ''

# Aplica a função a cada linha do DataFrame original
df_condicoes = tabela_situacoes.T.apply(criar_condicao, axis=1)
df_situacoes_logica = pd.DataFrame(df_condicoes, columns=['CONDICAO'])

df_situacoes_logica.to_excel('resultado/20241209_tabela_situacoes_inconformes_por_auditados_logica.xlsx')

with open("resultado/auditados.pkl", "wb") as f:
    pickle.dump(auditados, f)
import io
import os
import json
import time
import tempfile
from itertools import islice

from datetime import datetime
import zipfile
import streamlit as st

import pandas as pd
from jinja2 import Environment, BaseLoader, StrictUndefined
from google import genai
import re
from google.genai import types

from utils import avalia_gemini

st.set_page_config(page_title="Análise de Auditados com IA", layout="wide")

st.title("Análise de Auditados com IA (Gemini)")
st.write(
    "Use o poder do Gemini para analisar documentos associados aos auditados. "
    "Forneça sua chave de API, um prompt detalhado e os arquivos de contexto para obter um resultado estruturado."
)

if 'audit_results' not in st.session_state or not st.session_state.audit_results:
    st.info("Nenhum resultado de auditoria carregado. Por favor, carregue os resultados na página 'Aplicar Procedimentos' ou 'Carregar Resultado' para usar esta funcionalidade.")
    st.stop()

# --- 1. Configuração da API Key ---
st.subheader("1. Configure sua API Key do Google Gemini")
api_key = st.text_input(
    "GEMINI_API_KEY",
    type="password",
    help="Sua chave não será armazenada. É necessária para cada sessão."
)

if not api_key:
    st.warning("Por favor, insira sua GEMINI_API_KEY para continuar.")
    st.stop()

try:
    # Cria o cliente da API Gemini
    client = genai.Client(api_key=api_key)
except Exception as e:
    st.error(f"Erro ao criar o cliente da API do Gemini. Verifique se a chave é válida. Detalhes: {e}")
    st.stop()

# --- Seleção do Modelo Gemini ---
st.subheader("1.1. Selecione o Modelo Gemini")

model_options = {
    "Gemini 2.5 Flash": "gemini-2.5-flash",
    "Gemini 2.5 Latest": "gemini-2.5-flash-latest",
    "Gemini 2.5 Pro": "gemini-2.5-pro"
}

selected_model_display = st.selectbox(
    "Escolha o modelo Gemini para a análise:",
    options=list(model_options.keys())
)
selected_model_id = model_options[selected_model_display]

# --- 2. Entrada do Usuário ---
st.subheader("2. Forneça o Prompt e os Arquivos de Contexto")
with st.expander('Exemplos de Prompts Disponíveis'):
    prompts_dir = "prompts"
    if os.path.exists(prompts_dir) and os.path.isdir(prompts_dir):
        prompt_files = [f for f in os.listdir(prompts_dir) if f.endswith('.md')]
        if prompt_files:
            for prompt_file in prompt_files:
                filepath = os.path.join(prompts_dir, prompt_file)
                description = "Sem descrição."
                content = ""
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        first_line = content.split('\n', 1)[0]
                        # Extrai a descrição de um comentário HTML, ex: <!-- desc: Minha descrição. -->
                        match = re.search(r'<!--\s*desc:\s*(.*?)\s*-->', first_line)
                        if match:
                            description = match.group(1)
                except Exception:
                    pass # Usa a descrição padrão se houver erro
                with st.expander(f"**{prompt_file}**: {description}"):
                    st.code(content, language='markdown')
        else:
            st.info("Nenhum arquivo de prompt (.md) encontrado no diretório 'prompts/'.")
    else:
        st.info("O diretório 'prompts/' não foi encontrado para carregar exemplos.")

prompt_template = st.text_area(
    "Escreva seu prompt com Jinja2 aqui (variáveis como {{ auditado.nome }} e da planilha de contexto estão disponíveis):",
    height=200,
    placeholder="Exemplo: Analise os documentos de contexto fornecidos, que são relatórios de auditoria. "
                "Para cada relatório, extraia o nome do auditado, os principais achados e os encaminhamentos. "
                "Retorne o resultado em formato JSON, com uma lista de objetos, onde cada objeto representa um auditado."
)

col1, col2 = st.columns(2)
with col1:
    response_format = st.radio(
        "Formato da Resposta:",
        ("Texto", "Estruturada"),
        horizontal=True,
        help="Selecione Estruturada para instruir o modelo a retornar uma saída estruturada em formato de planilha."
    )
with col2:
    temperature = st.slider(
        "Temperatura:", min_value=0.0, max_value=2.0, value=0.0, step=0.1,
        help="Valores mais baixos geram respostas mais determinísticas. Valores mais altos geram respostas mais criativas."
    )

st.markdown("---")
st.subheader("2.1. Forneça dados de contexto adicionais (Opcional)")

arquivo_contexto_excel = st.file_uploader("Carregar Planilha de Contexto (.xlsx)", type=["xlsx"], help="A planilha deve ter uma coluna 'sigla' para identificar o auditado e fornecer variáveis adicionais ao template.")
df_contexto_extra = None
if arquivo_contexto_excel:
    df_contexto_extra = pd.read_excel(arquivo_contexto_excel)
    if 'sigla' not in df_contexto_extra.columns:
        st.error("A planilha de contexto deve conter uma coluna 'sigla'.")
        st.stop()
    df_contexto_extra = df_contexto_extra.set_index('sigla')
    df_contexto_extra.columns = [col.strip() for col in df_contexto_extra.columns]

    cols_to_rename = {}
    # Trata colunas que terminam com '*' para converter strings separadas por '|' em listas
    for col in df_contexto_extra.columns:
        if col.endswith('*'):
            df_contexto_extra[col] = df_contexto_extra[col].apply(
                lambda x: [item.strip() for item in str(x).split('|')] if pd.notna(x) else []
            )
            cols_to_rename[col] = col.rstrip('*')

    # Renomeia as colunas que foram processadas
    if cols_to_rename:
        df_contexto_extra.rename(columns=cols_to_rename, inplace=True)
    st.dataframe(df_contexto_extra.head())

context_files = st.file_uploader(
    "Carregue seus arquivos de contexto (.txt, .pdf, .csv, .zip etc)",
    accept_multiple_files=True
)

st.markdown("---")
st.subheader("2.2. Retomar Análise Anterior (Opcional)")
arquivo_resumo_excel = st.file_uploader(
    "Carregar Planilha Consolidada Anterior (.xlsx)",
    type=["xlsx"],
    help="Carregue uma planilha gerada anteriormente para pular os auditados já analisados."
)
df_resumo = None
siglas_ja_analisadas = set()
if arquivo_resumo_excel:
    df_resumo = pd.read_excel(arquivo_resumo_excel)
    if 'auditado_sigla' in df_resumo.columns:
        siglas_ja_analisadas = set(df_resumo['auditado_sigla'].unique())
        st.success(f"Planilha de resumo carregada. {len(siglas_ja_analisadas)} auditados serão pulados se encontrados.")
    else:
        st.error("A planilha de resumo não contém a coluna 'auditado_sigla' e não pode ser usada para retomar a análise.")
        df_resumo = None # Invalida o dataframe se a coluna chave não existir

st.markdown("---")
st.subheader("3. Gere a Análise")

# Inicializa o ambiente Jinja2
jinja_env = Environment(loader=BaseLoader(), undefined=StrictUndefined)

if st.button("Analisar com Gemini"):
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 5

    if not prompt_template:
        st.error("O campo de prompt não pode estar vazio.")
    else:
        with st.spinner("Analisando documentos... Isso pode levar alguns minutos."):
            try:
                all_results = []

                results = st.session_state.audit_results
                # auditados = dict(islice(results["auditados"].items(), 2))
                auditados = results["auditados"]

                st.info(f"Detectados {len(auditados)} auditados. A análise será realizada para cada um.")

                # Armazena response_format e temperature no estado da sessão para uso posterior na exibição
                st.session_state.last_response_format = response_format
                st.session_state.last_temperature = temperature

                # Mapeia todos os arquivos carregados (incluindo os de ZIPs) pelo nome para fácil acesso
                available_files_map = {}
                if context_files:
                    for uploaded_file in context_files:
                        if uploaded_file.name.lower().endswith('.zip'):
                            st.info(f"📦 Indexando arquivos de '{uploaded_file.name}'...")
                            with zipfile.ZipFile(uploaded_file, 'r') as zip_ref:
                                for file_info in zip_ref.infolist():
                                    if not file_info.is_dir():
                                        file_bytes = io.BytesIO(zip_ref.read(file_info.filename))
                                        file_bytes.name = file_info.filename
                                        available_files_map[file_info.filename] = file_bytes
                        else:
                            available_files_map[uploaded_file.name] = uploaded_file


                st.markdown("##### Analisando")
                for sigla, auditado_obj in auditados.items():
                    if sigla in siglas_ja_analisadas:
                        st.info(f"Auditado {auditado_obj.nome} ({sigla}) já presente na planilha de resumo. Pulando.")
                        # Adiciona os dados existentes do resumo aos resultados para que a seção de download funcione
                        df_auditado_existente = df_resumo[df_resumo['auditado_sigla'] == sigla]
                        all_results.append({
                            "auditado_sigla": sigla,
                            "auditado_nome": auditado_obj.nome,
                            "resposta_gemini": df_auditado_existente
                        })
                        continue

                    with st.expander(f"**{auditado_obj.nome} ({sigla})**"):
                        uploaded_file_objects = []

                        # Separa os arquivos específicos para o auditado
                        required_filenames = []
                        if df_contexto_extra is not None and sigla in df_contexto_extra.index:
                            auditado_context_row = df_contexto_extra.loc[sigla]
                            # 'cols_to_rename' foi definido durante o processamento da planilha
                            for col_name in cols_to_rename.values(): # Itera sobre os nomes de coluna já limpos (sem '*')
                                if col_name in auditado_context_row and isinstance(auditado_context_row[col_name], list):
                                    required_filenames.extend(auditado_context_row[col_name])

                        if not required_filenames:
                            st.warning(f"Nenhum arquivo de contexto especificado para '{sigla}'. A análise prosseguirá sem arquivos.")
                        else:
                            st.write(f"Arquivos de contexto para '{sigla}':")
                            for filename in required_filenames:
                                if filename in available_files_map:
                                    file_to_upload = available_files_map[filename]

                                    # Extrai a extensão do arquivo original para usar como sufixo no arquivo temporário
                                    # Isso garante que NamedTemporaryFile crie um arquivo plano no diretório /tmp
                                    file_extension = os.path.splitext(os.path.basename(file_to_upload.name))[1]

                                    with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                                            tmp_file.write(file_to_upload.getvalue())
                                            tmp_file_path = tmp_file.name
                                    st.info(f"📄 Fazendo upload de '{file_to_upload.name}' para a API...")
                                    uploaded_file_objects.append(client.files.upload(file=tmp_file_path))
                                    os.remove(tmp_file_path)
                                else:
                                    st.error(f"Arquivo '{filename}' especificado para '{sigla}' não encontrado nos arquivos carregados.")

                        # Monta o contexto específico do auditado para o Jinja2
                        contexto_render = {'auditado': auditado_obj}
                        if df_contexto_extra is not None and sigla in df_contexto_extra.index:
                            contexto_render.update(df_contexto_extra.loc[sigla].to_dict())

                        # Renderiza o prompt com o contexto do auditado atual
                        template = jinja_env.from_string(prompt_template)
                        rendered_prompt = template.render(contexto_render)

                        st.expander(f"Prompt Final para {sigla} (clique para expandir)").code(rendered_prompt)

                        # Gera o conteúdo usando o cliente e o modelo selecionado
                        response = None
                        error_message = None
                        for attempt in range(MAX_RETRIES):
                            response, error_message = avalia_gemini(client, rendered_prompt, selected_model_id, temperature, response_format, uploaded_file_objects)

                            if not error_message:
                                st.success(f"Análise para {sigla} bem-sucedida.")
                                break  # Sucesso, sai do loop de tentativas

                            st.warning(f"Tentativa {attempt + 1}/{MAX_RETRIES} para {sigla} falhou. Erro: {error_message}")
                            if attempt < MAX_RETRIES - 1:
                                with st.spinner(f"Aguardando {RETRY_DELAY_SECONDS} segundos antes de tentar novamente..."):
                                    time.sleep(RETRY_DELAY_SECONDS)


                        if error_message:
                            st.error(f"Falha ao analisar {sigla} após {MAX_RETRIES} tentativas. Erro final: {error_message}")
                            all_results.append({
                                "auditado_sigla": sigla,
                                "auditado_nome": auditado_obj.nome,
                                "resposta_gemini": error_message
                            })
                            continue # Pula para o próximo auditado em caso de erro

                        # Exibe o resultado imediatamente dentro de um expander
                        with st.expander(f"Resultado", expanded=True):
                            if response_format == 'Estruturada':
                                try:
                                    datahora_atual = datetime.now()

                                    # Tenta processar o JSON e mostrar um preview do DataFrame
                                    response_json = json.loads(response.text)
                                    df = pd.json_normalize(response_json)
                                    df['auditado_sigla'] = sigla
                                    df['auditado_nome'] = auditado_obj.nome
                                    df['data_avaliacao'] = datahora_atual
                                    df['modelo'] = selected_model_id

                                    st.markdown("##### Planilha Gerada:")
                                    st.dataframe(df.head())

                                    response_modelo = df
                                except (json.JSONDecodeError, TypeError) as e:
                                    st.error(f"A resposta do modelo não é um JSON válido. Exibindo como texto. Erro: {e}")
                                    st.text(response.text)
                                    response_modelo = response.text

                            else: # Caso seja 'Texto'
                                st.markdown(response.text)
                                response_modelo = response.text

                        all_results.append({
                            "auditado_sigla": sigla,
                            "auditado_nome": auditado_obj.nome,
                            "resposta_gemini": response_modelo
                        })

                st.session_state.gemini_results = all_results
                with st.spinner("Aguardando tempo de espera."):
                    time.sleep(2)

            except Exception as e:
                st.error(f"Ocorreu um erro durante a chamada para a API do Gemini: {e}")

# --- 4. Exibição do Resultado ---
if 'gemini_results' in st.session_state and st.session_state.gemini_results:
    st.markdown("---")
    st.subheader("4. Baixar Resultados")
    st.markdown("Use os botões abaixo para baixar os resultados individuais ou um arquivo consolidado.")

    # Listas para armazenar dados para download consolidado
    dfs_results_for_excel = []
    all_md_files_for_zip = []

    st.markdown("##### Downloads Individuais")
    # Cria um cabeçalho para a tabela de downloads
    header_cols = st.columns([3, 1])
    with header_cols[0]:
        st.markdown("**Auditado**")
    with header_cols[1]:
        st.markdown("**Ação**")

    for idx, result in enumerate(st.session_state.gemini_results):
        deu_problema = False
        response_modelo = result['resposta_gemini']

        if st.session_state.get('last_response_format') == 'Estruturada':
            if isinstance(response_modelo, pd.DataFrame):
                dfs_results_for_excel.append(response_modelo)
            else:
                deu_problema = True
        else: # Se o formato for 'Texto'
            md_filename = f"resultado_{result.get('auditado_sigla', 'unico')}.md"
            all_md_files_for_zip.append((md_filename, response_modelo))

        # Cria as colunas para cada linha de resultado
        row_cols = st.columns([3, 1], border=True)
        with row_cols[0]:
            st.write(f"{result.get('auditado_nome', 'N/A')} ({result.get('auditado_sigla', 'N/A')})")
        with row_cols[1]:
            if deu_problema:
                st.write('❌ Erro na avaliação')
            else:
                data_for_download = None
                download_filename = ""
                download_mime = ""

                if isinstance(response_modelo, pd.DataFrame):
                    download_filename = f"resultado_{result.get('auditado_sigla', 'unico')}.xlsx"
                    download_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    excel_buffer = io.BytesIO()
                    response_modelo.to_excel(excel_buffer, index=False, engine='xlsxwriter')
                    data_for_download = excel_buffer.getvalue()
                elif isinstance(response_modelo, str):
                    download_filename = f"resultado_{result.get('auditado_sigla', 'unico')}.md"
                    download_mime = "text/markdown"
                    data_for_download = response_modelo.encode('utf-8') # Garante que seja bytes
                else:
                    st.error(f"Tipo de dado inesperado para download: {type(response_modelo)}")
                    # Não exibe o botão de download se o tipo for desconhecido
                    pass

                if data_for_download is not None:
                    st.download_button(
                        label="Baixar",
                        data=data_for_download,
                        file_name=download_filename,
                        mime=download_mime,
                        key=f"download_individual_{idx}",
                        icon=":material/download:"
                    )

    st.markdown("---") # Separador visual
    # Botão para download consolidado
    st.markdown("##### Downloads Consolidados")
    if st.session_state.get('last_response_format') == 'Estruturada' and dfs_results_for_excel:
        st.info("Gera uma única planilha Excel com os resultados de todas as análises.")
        try:
            # # Se uma planilha de resumo foi carregada, adiciona seus dados à lista para concatenação
            # if df_resumo is not None:
            #     dfs_results_for_excel.insert(0, df_resumo)

            df_agregado = pd.concat(dfs_results_for_excel, ignore_index=True)

            excel_buffer = io.BytesIO()
            df_agregado.to_excel(excel_buffer, index=False, engine='xlsxwriter')
            excel_buffer.seek(0)

            st.download_button(
                label="Baixar Resultados Estruturados Consolidados (.xlsx)",
                data=excel_buffer,
                file_name="resultados_gemini_consolidados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_json_excel_consolidated"
            )
        except Exception as e:
            st.error(f"Erro ao gerar planilha Excel a partir dos resultados estruturados: {e}")

    if st.session_state.get('last_response_format') == 'Texto' and all_md_files_for_zip:
        st.info("Gere um arquivo .ZIP contendo todos os relatórios de texto individuais.")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for filename, data in all_md_files_for_zip:
                zip_file.writestr(filename, data.encode('utf-8'))
        zip_buffer.seek(0)
        st.download_button(
            label="📥 Baixar Todos os Relatórios (.zip)",
            data=zip_buffer,
            file_name="relatorios_gemini.zip",
            mime="application/zip"
        )

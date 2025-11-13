import io
import os
import json
import tempfile

import streamlit as st

import pandas as pd
from jinja2 import Environment, BaseLoader, StrictUndefined
from google import genai
from google.genai import types

from utils import avalia_gemini

st.set_page_config(page_title="Análise de Auditados com IA", layout="wide")

st.title("🤖 Análise de Auditados com IA (Gemini)")
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
        ("Texto", "JSON"),
        horizontal=True,
        help="Selecione JSON para instruir o modelo a retornar uma saída estruturada."
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
    df_contexto_extra = pd.read_excel(arquivo_contexto_excel).set_index('sigla')
    df_contexto_extra.columns = [col.strip() for col in df_contexto_extra.columns]
    st.dataframe(df_contexto_extra.head())

context_files = st.file_uploader(
    "Carregue seus arquivos de contexto (.txt, .pdf, .csv etc)",
    accept_multiple_files=True
)

# --- 3. Geração do Resultado ---
st.subheader("3. Gere a Análise")

# Inicializa o ambiente Jinja2
jinja_env = Environment(loader=BaseLoader(), undefined=StrictUndefined)

if st.button("Analisar com Gemini"):
    if not prompt_template:
        st.error("O campo de prompt não pode estar vazio.")
    else:
        with st.spinner("Analisando documentos... Isso pode levar alguns minutos."):
            try:
                all_results = []
                
                results = st.session_state.audit_results
                auditados = results["auditados"]
                st.info(f"Detectados {len(auditados)} auditados. A análise será realizada para cada um.")

                # Armazena response_format e temperature no estado da sessão para uso posterior na exibição
                st.session_state.last_response_format = response_format
                st.session_state.last_temperature = temperature

                for sigla, auditado_obj in auditados.items():
                    st.subheader(f"Analisando Auditado: {auditado_obj.nome} ({sigla})")
                    
                    # Monta o contexto para o template Jinja2
                    contexto_render = {'auditado': auditado_obj}
                    if df_contexto_extra is not None and sigla in df_contexto_extra.index:
                        contexto_render.update(df_contexto_extra.loc[sigla].to_dict())
                    else:
                        st.warning(f"Auditado '{sigla}' não encontrado na planilha de contexto. Apenas o objeto 'auditado' estará disponível.")

                    # Renderiza o prompt com o contexto do auditado atual
                    template = jinja_env.from_string(prompt_template)
                    rendered_prompt = template.render(contexto_render)
                    
                    st.expander(f"Prompt Final para {sigla} (clique para expandir)").code(rendered_prompt)

                    # Prepara o conteúdo para a API, começando com o prompt
                    uploaded_file_objects = []

                    if context_files:
                        st.write("Arquivos de contexto carregados para esta análise:")
                        for file in context_files:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.name}") as tmp_file:
                                tmp_file.write(file.getvalue())
                                tmp_file_path = tmp_file.name
                            
                            st.info(f"📄 Fazendo upload de '{file.name}' para a API...")
                            uploaded_file_obj = client.files.create(file=tmp_file_path)
                            uploaded_file_objects.append(uploaded_file_obj)
                            os.remove(tmp_file_path)
                    else:
                        st.warning("Nenhum arquivo de contexto carregado para esta análise.")

                    # Gera o conteúdo usando o cliente e o modelo selecionado
                    response, error_message = avalia_gemini(client, rendered_prompt, selected_model_id, temperature, response_format, uploaded_file_objects)
                    
                    if error_message:
                        st.error(error_message)
                        continue # Pula para o próximo auditado em caso de erro

                    all_results.append({
                        "auditado_sigla": sigla,
                        "auditado_nome": auditado_obj.nome,
                        "resposta_gemini": response.text
                    })

                st.session_state.gemini_results = all_results
            except Exception as e:
                st.error(f"Ocorreu um erro durante a chamada para a API do Gemini: {e}")

# --- 4. Exibição do Resultado ---
if 'gemini_results' in st.session_state and st.session_state.gemini_results:
    st.subheader("Resultado da Análise")
    
    json_results_for_excel = []
    for idx, result in enumerate(st.session_state.gemini_results):
        if "auditado_sigla" in result:
            st.markdown(f"### Resultado para {result.get('auditado_nome', 'N/A')} ({result.get('auditado_sigla', 'N/A')})")
        else:
            st.markdown(f"### Resultado da Análise Única")
            
        result_text = result['resposta_gemini']
        
        # Tenta detectar se o resultado é JSON para uma exibição mais bonita e para agregação
        if st.session_state.get('last_response_format') == 'JSON':
            try:
                parsed_json = json.loads(result_text)
                # Se o JSON for uma lista, estende a lista. Se for um objeto, anexa-o.
                if isinstance(parsed_json, list):
                    for item in parsed_json:
                        # Adiciona informações do auditado a cada item se for uma lista de objetos
                        item_with_auditado_info = {
                            "auditado_sigla": result.get('auditado_sigla', 'N/A'),
                            "auditado_nome": result.get('auditado_nome', 'N/A'),
                            **item
                        }
                        json_results_for_excel.append(item_with_auditado_info)
                elif isinstance(parsed_json, dict):
                    # Adiciona informações do auditado ao objeto
                    obj_with_auditado_info = {
                        "auditado_sigla": result.get('auditado_sigla', 'N/A'),
                        "auditado_nome": result.get('auditado_nome', 'N/A'),
                        **parsed_json
                    }
                    json_results_for_excel.append(obj_with_auditado_info)
            except json.JSONDecodeError:
                st.warning(f"Não foi possível parsear o JSON para {result.get('auditado_sigla', 'Análise Única')}. Verifique o formato.")
        if result_text.strip().startswith('{') or result_text.strip().startswith('['):
            st.json(result_text)
        else:
            st.markdown(result_text)
            
        download_filename = f"resultado_gemini_{result.get('auditado_sigla', 'unico')}_{idx}.md"
        st.download_button(
            f"Baixar Resultado para {result.get('auditado_sigla', 'Análise Única')}",
            result_text,
            download_filename,
            key=f"download_btn_{idx}"
        )
        st.markdown("---") # Separador entre resultados

    # Se o formato de saída foi JSON e há resultados para agregar, oferece o download em Excel
    if st.session_state.get('last_response_format') == 'JSON' and json_results_for_excel:
        try:
            df_json_results = pd.DataFrame(json_results_for_excel)
            excel_buffer = io.BytesIO()
            df_json_results.to_excel(excel_buffer, index=False, engine='xlsxwriter')
            excel_buffer.seek(0)

            st.download_button(
                label="Baixar Resultados JSON Consolidados (.xlsx)",
                data=excel_buffer,
                file_name="resultados_gemini_consolidados.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_json_excel_consolidated"
            )
        except Exception as e:
            st.error(f"Erro ao gerar planilha Excel a partir dos resultados JSON: {e}")

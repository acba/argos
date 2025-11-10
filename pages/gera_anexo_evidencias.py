import streamlit as st
import pandas as pd
import io
import zipfile
import logging
import pypandoc
from docxtpl import DocxTemplate
from jinja2 import Environment, BaseLoader, StrictUndefined, exceptions

from classes import gerar_tabela_achados
from utils import get_variaveis_template, StreamlitLogHandler

st.set_page_config(page_title="Gerar Relatórios", layout="wide")

st.title("Gera Anexo Evidências")
st.write("Esta seção permite a geração do papel de trabalho que contém a relação de evidências por auditado a partir dos dados de auditoria processados.")

if st.session_state.audit_completed:
    results = st.session_state.audit_results
    auditados = results["auditados"]

    if st.button("Gerar Anexo de Evidências"):
        with st.spinner("Gerando anexo..."):
            contexto_anexo = [{'sigla_orgao': a.sigla, 'nome_orgao': a.nome, 'achados': list(a.get_achados().values())} for a in auditados.values()]
            base = DocxTemplate("docs/anexo-evidencias-base.docx")
            base.render({'dados': contexto_anexo})
            bio = io.BytesIO()
            base.save(bio)
            st.session_state.download_files['relatorio_evidencias'] = bio.getvalue()

    if 'relatorio_evidencias' in st.session_state.download_files:
        st.download_button(
            label="Baixar Anexo de Evidências",
            data=st.session_state.download_files['relatorio_evidencias'],
            file_name="ANXX - Evidências.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

else:
    st.info("Por favor, aplique os procedimentos ou carregue um resultado de auditoria antes de gerar relatórios.")
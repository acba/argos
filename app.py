import streamlit as st
import os

os.makedirs('tmp', exist_ok=True)

# Configuração da página principal
st.set_page_config(
    page_title="Argos - Auditoria Simplificada",
    layout="wide"
)

st.logo('img/argos_logo.png', size='large')


if 'configurado' not in st.session_state:
    st.session_state.configurado = True

# Inicializa o estado da sessão para manter os resultados após o download
# Isso garante que o estado seja compartilhado entre as páginas.
if 'files_processed' not in st.session_state:
    st.session_state.files_processed = False
if 'audit_completed' not in st.session_state:
    st.session_state.audit_completed = False
if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None
if 'download_files' not in st.session_state:
    st.session_state.download_files = {}


home_page = st.Page("pages/home.py", title="Home", default=True)
aplica_procedimento_page = st.Page('pages/aplica_procedimentos.py', title="Aplica Procedimentos")
carrega_auditoria_page = st.Page('pages/carrega_auditoria.py', title="Carregar Resultado")
visualiza_resultados_page = st.Page('pages/visualiza_resultados.py', title="Visualiza Resultado")
gera_relatorios_individuais_page = st.Page('pages/gera_relatorios.py', title="Gera Relatórios Individuais")
gera_anexo_evidencias_page = st.Page('pages/gera_anexo_evidencias.py', title="Gera Anexo Evidências")

pg = st.navigation(
    {
        "Procedimentos": [home_page, aplica_procedimento_page, carrega_auditoria_page, visualiza_resultados_page],
        "Relatório": [gera_relatorios_individuais_page, gera_anexo_evidencias_page],
    }
)

pg.run()

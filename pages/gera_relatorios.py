import streamlit as st
import pandas as pd
import io
import zipfile
import logging
import pypandoc
import docx

from docxtpl import DocxTemplate
from jinja2 import Environment, BaseLoader, StrictUndefined, exceptions

from classes import gerar_tabela_achados
from utils import get_variaveis_template, StreamlitLogHandler

st.set_page_config(page_title="Gera Relatórios Individuais", layout="wide")

st.title("Gera Relatórios Individuais")
st.write("Esta seção permite a geração de relatórios personalizados a partir dos dados de auditoria processados, usando templates em formato Markdown/Jinja2.")

if st.session_state.audit_completed:
    results = st.session_state.audit_results
    auditados = results["auditados"]

    col1, col2 = st.columns(2)
    with col1:
        st.write("Auditados:")
        df_auditados = pd.DataFrame([{'sigla': a.sigla, 'nome': a.nome} for a in auditados.values()]).set_index('sigla')
        st.dataframe(df_auditados, height=200)
    with col2:
        st.write("Achados:")
        df_achados = pd.DataFrame([{'nome': nome} for nome in gerar_tabela_achados(auditados).columns])
        st.dataframe(df_achados, height=200)

    st.subheader("1. Forneça dados de contexto adicionais (Opcional)")
    arquivo_contexto = st.file_uploader("Carregar Planilha de Contexto (.xlsx)", type=["xlsx"], help="A planilha deve ter uma coluna 'sigla' para identificar o auditado.")
    df_contexto_extra = None
    if arquivo_contexto:
        df_contexto_extra = pd.read_excel(arquivo_contexto).set_index('sigla')
        st.dataframe(df_contexto_extra.head())

    arquivos_fontes_contexto = st.file_uploader("Arquivos presentes na planilha de contexto", accept_multiple_files=True)

    st.subheader("2. Forneça o template do relatório")
    col1, col2 = st.columns(2)
    with col1:
        arquivo_template_md = st.file_uploader("Carregue um arquivo de template (.md, .jinja)", type=["md", "jinja"])
    with col2:
        arquivo_template_docx = st.file_uploader("Carregue um arquivo de template (.docx)", type=["docx"])

    template_content = None
    if arquivo_template_md:
        try:
            template_content = arquivo_template_md.read().decode('utf-8')
        except Exception as e:
            st.error(f"Erro ao ler o arquivo .md: {e}")

    if arquivo_template_docx:
        try:
            doc = docx.Document(arquivo_template_docx)
            template_content = "\n".join([para.text for para in doc.paragraphs])
            template_content = template_content.replace("%p", "%").replace('‘', "'").replace('’', "'").replace('“', "'").replace('”', "'")
        except Exception as e:
            st.error(f"Erro ao ler o arquivo .docx: {e}")

    if template_content:
        with st.expander("Conteúdo do template:"):
            st.code(template_content)

        vars_template = get_variaveis_template(template_content)
        st.write("Variáveis encontradas no template:")
        st.code(f"{vars_template}")

    st.subheader("3. Gere os relatórios")
    if st.button("Gerar Relatórios Individuais"):
        # Processamento do template markdown
        with st.spinner("Gerando relatórios individuais..."):
            env = Environment(loader=BaseLoader(), undefined=StrictUndefined)
            template_ref_docx = 'docs/template-relatorio-individual.docx'
            generation_log = st.expander("Log de Geração", expanded=True)
            zip_buffer = io.BytesIO()

            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_f:
                for sigla, row_auditado in df_auditados.iterrows():
                    with generation_log:
                        st.markdown(f"--- \n#### Processando: **{sigla}**")
                        contexto = row_auditado.to_dict()
                        contexto['sigla'] = sigla

                        if df_contexto_extra is not None and sigla in df_contexto_extra.index:
                            contexto.update(df_contexto_extra.loc[sigla].to_dict())
                        contexto['auditado'] = auditados[sigla]

                        vars_faltantes = set(vars_template) - set(contexto.keys())
                        if len(vars_faltantes):
                            st.warning(f'Atenção: As seguintes variáveis estão sendo utilizadas no template, mas não existem nos dados do contexto: {", ".join(vars_faltantes)}')
                            st.warning('Para não impedir o processamento da geração, serão preenchidos dados vazios para essas variáveis.')
                            for var in vars_faltantes:
                                contexto[var] = []

                        if arquivo_template_md:
                            try:
                                template_md = env.from_string(template_content)
                                conteudo_final_md = template_md.render(contexto)

                                md_filename = f'tmp/relatorio-{sigla}.md'
                                with open(md_filename, 'w', encoding='utf-8') as f:
                                    f.write(conteudo_final_md)

                                docx_filename = f'tmp/relatorio-{sigla}.docx'
                                args_docx = ['--reference-doc=' + template_ref_docx]
                                pypandoc_logger = logging.getLogger('pypandoc')
                                pypandoc_logger.setLevel(logging.WARNING)
                                log_container = st.empty()
                                handler = StreamlitLogHandler(log_container)
                                pypandoc_logger.addHandler(handler)

                                pypandoc.convert_file(md_filename, to='docx', outputfile=docx_filename, extra_args=args_docx)
                                pypandoc_logger.removeHandler(handler)

                                if not handler.records: st.success(f"Relatório para **{sigla}** gerado.")
                                zip_f.write(docx_filename, arcname=f'Relatorio-{sigla}.docx')

                            except exceptions.UndefinedError as e:
                                st.error(f"**Erro no template para `{sigla}`:** A variável `{e.message.split(' is undefined')[0]}` não foi encontrada.")
                            except Exception as e:
                                st.error(f"Erro ao gerar relatório para **{sigla}**: {e}")
                        elif arquivo_template_docx:
                            base_docx = DocxTemplate(arquivo_template_docx)
                            base_docx.render(contexto)

                            bio = io.BytesIO()
                            base_docx.save(bio)

                            zip_f.writestr(f"Relatorio-{sigla}.docx", bio.getvalue())
                            st.success(f"Relatório para **{sigla}** gerado.")

                        else:
                            st.error("Por favor, forneça um template (colando o texto ou carregando o arquivo).")

            st.session_state.download_files['relatorios_individuais_zip'] = zip_buffer.getvalue()
        st.success("Geração de relatórios concluída!")

    if 'relatorios_individuais_zip' in st.session_state.download_files:
        st.download_button(
            label="Baixar Todos os Relatórios Individuais (.zip)",
            data=st.session_state.download_files['relatorios_individuais_zip'],
            file_name="relatorios_individuais.zip",
            mime="application/zip"
        )

else:
    st.info("Por favor, aplique os procedimentos ou carregue um resultado de auditoria antes de gerar relatórios.")
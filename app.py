import streamlit as st
import pandas as pd
import re
import os
import io
import logging
import pickle
import zipfile
from docxtpl import DocxTemplate, RichText, InlineImage
from jinja2 import Environment, FileSystemLoader, BaseLoader, StrictUndefined
import jinja2.meta
import pypandoc

from classes import FonteInformacao, Achado, AcaoVerificacao, ProcedimentoAuditoria, Auditado, \
    gerar_tabela_encaminhamentos, gerar_tabela_achados, gerar_tabela_situacoes_inconformes

os.makedirs('tmp', exist_ok=True)

# Funções auxiliares para carregar os dados dos arquivos Excel
def carregar_dados(filepath, sheet_name=0, skiprows=2):
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
    vars_template = jinja2.meta.find_undeclared_variables(ast)
    return vars_template

# Handler de logging customizado para capturar logs do pypandoc e exibi-los no Streamlit
class StreamlitLogHandler(logging.Handler):
    def __init__(self, container):
        super().__init__()
        self.container = container
        self.records = []

    def emit(self, record):
        self.records.append(record)
        msg = self.format(record)
        # Exibe a mensagem de warning no container do Streamlit
        self.container.warning(msg)


# Inicializa o estado da sessão para manter os resultados após o download
if 'files_processed' not in st.session_state:
    st.session_state.files_processed = False
if 'audit_completed' not in st.session_state:
    st.session_state.audit_completed = False
if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None
if 'download_files' not in st.session_state:
    st.session_state.download_files = {}

st.sidebar.title("Argos - Auditoria Simplificada")

page = st.sidebar.radio("Navegação", [
    "1. Aplicar Procedimentos de Auditoria",
    "1. Carregar resultado de auditoria",
    "2. Visualizar resultado de auditoria",
    "3. Gerar Relatórios"
])

if page == "1. Aplicar Procedimentos de Auditoria": # Início da página "Aplicar Procedimentos de Auditoria"
    st.title("1. Aplicar Procedimentos de Auditoria")
    st.write("Esta seção realiza a aplicação dos procedimentos de auditoria definidos no mapa de verificação de achados. O processo gera como saída o objeto no modelo de dados do Audita, planilhas apresentando relação achados, encaminhamentos e situações encontrados por auditado, e relatórios individuais da aplicação dos procedimentos nos auditados.")

    with st.expander("Modelo de Dados do Audita"):
        st.image('mermaid-diagram.png')

    # 1. Upload dos arquivos Excel
    with st.expander("1. Carregar Arquivos Excel", expanded=True):
        arquivo_auditados = st.file_uploader("Base de Auditados (ex: base-auditados.xlsx)", type=["xlsx"])
        arquivo_mapa_achados  = st.file_uploader("Mapa de Verificação e Achados (ex: mapa-verificacao-achados.xlsx)", type=["xlsx"])
        arquivos_fontes_dados = st.file_uploader("Fontes de Informação (arquivos .xlsx)", type=["xlsx"], accept_multiple_files=True)

        if not arquivo_auditados or not arquivo_mapa_achados or not arquivos_fontes_dados:
            st.info("Por favor, carregue todos os arquivos Excel de entrada.")

    # 2. Processamento dos dados
    if arquivo_auditados and arquivo_mapa_achados and arquivos_fontes_dados:
        if st.button("Processar arquivos e gerar achados"):
            # st.header("2. Processando Dados e Gerando Resultados")
            st.session_state.files_processed = False
            st.session_state.audit_completed = False
            st.session_state.audit_results = None

            try:
                if not st.session_state.files_processed:
                    # Leitura dos DataFrames
                    with st.spinner("Carregando planilhas..."):
                        df_jurisdicionados = carregar_dados(arquivo_auditados, skiprows=0)

                        df_procedimentos = carregar_dados(arquivo_mapa_achados, sheet_name='Procedimentos de Auditoria')
                        df_acoes_verificacao = carregar_dados(arquivo_mapa_achados, sheet_name='Ações de Verificação')
                        df_fontes = carregar_dados(arquivo_mapa_achados, sheet_name='Fontes de Informação')

                        # Verificação se os DataFrames foram carregados corretamente
                        if any(df is None for df in [df_jurisdicionados, df_procedimentos, df_acoes_verificacao, df_fontes]):
                            st.error("Erro ao carregar uma ou mais planilhas. Verifique os arquivos e se as abas ('Procedimentos de Auditoria', 'Ações de Verificação', 'Fontes de Informação') existem.")
                            st.stop()

                    # Mapeia os arquivos de fonte de dados carregados pelo nome
                    fontes_dados_carregadas = {f.name: f for f in arquivos_fontes_dados}

                    # 1. Leitura das fontes de informação
                    with st.spinner("Processando fontes de informação..."):
                        fontes = {}
                        for _, row in df_fontes.iterrows():
                            nome_arquivo_fonte = os.path.basename(row['filepath'])
                            fonte = FonteInformacao(
                                descricao=row['descricao'],
                                filepath=fontes_dados_carregadas.get(nome_arquivo_fonte),
                                chave_jurisdicionado=row['chave_jurisdicionado'],
                                id=row['id']
                            )
                            try:
                                fonte.read()
                                fontes[fonte.id] = fonte  # Armazena no dicionário para referência posterior
                            except IOError as e:
                                st.error(f"Erro ao carregar a fonte de informação '{fonte.descricao}': {e}")
                                # st.stop()
                            except AttributeError:
                                st.error(f"Arquivo da fonte de informação '{fonte.descricao}' ('{nome_arquivo_fonte}') não foi encontrado nos arquivos carregados. "
                                        f"Verifique se o arquivo foi carregado e se o nome corresponde ao da planilha 'Fontes de Informação'.")
                                # st.stop()

                    # 2. Leitura das ações de verificação
                    with st.spinner("Processando ações de verificação..."):
                        acoes = {}
                        for _, row in df_acoes_verificacao.iterrows():
                            fonte_informacao = fontes.get(row['id_fonte_informacao'])
                            if not fonte_informacao:
                                st.error(f"Ação de verificação '{row['id']}' refere-se a uma fonte de informação ('{row['id_fonte_informacao']}') que não foi encontrada. Verifique a planilha 'Ações de Verificação'.")
                                # st.stop()

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
                    with st.spinner("Processando procedimentos de auditoria..."):
                        procedimentos = {}
                        for _, row in df_procedimentos.iterrows():
                            procedimento = ProcedimentoAuditoria(
                                descricao=row['descricao'],
                                logica_achado=row['logica_achado'],
                                numero_achado=row['numero_achado'],
                                nome_achado=row['nome_achado'],
                                id=row['id']
                            )

                            # Adiciona as ações de verificação relevantes que constam na lógica do procedimento
                            # (AV03 | AV04 | AV05 | AV06 | AV07 | AV08 | AV09 | AV10 ) -> ['AV03', 'AV04' ...]
                            acao_ids = re.split(r'[\&\|\~\(\)\s]+', procedimento.logica_achado.replace("(", "").replace(")", ""))
                            acao_ids = [acao_id for acao_id in acao_ids if acao_id]

                            for acao_id in acao_ids:
                                acao = acoes.get(acao_id.strip())
                                if acao:
                                    procedimento.adicionar_acao(acao)
                            procedimentos[procedimento.id] = procedimento

                    # 4. Leitura dos auditados
                    with st.spinner("Carregando lista de auditados..."):
                        auditados = {}
                        for _, row in df_jurisdicionados.iterrows():
                            auditado = Auditado(
                                nome=row['orgao'],
                                sigla=row['sigla'],
                                # id=row['id']
                            )
                            auditados[auditado.sigla] = auditado

                    st.success("Arquivos carregados e processados com sucesso!")
                    st.session_state.files_processed = True

                # Se já carregou as planilhas mas ainda não finalizou a execução dos procedimentos
                if st.session_state.files_processed and st.session_state.audit_completed == False:
                    with st.spinner("Executando procedimentos de auditoria... Por favor, aguarde."):
                        # Execução da auditoria
                        for auditado in auditados.values():
                            auditado.aplicar_procedimentos(procedimentos.values(), debug=False)

                        # Geração das tabelas
                        tabela_encaminhamentos = gerar_tabela_encaminhamentos(auditados)
                        tabela_achados = gerar_tabela_achados(auditados)
                        tabela_situacoes = gerar_tabela_situacoes_inconformes(auditados)

                        st.session_state.audit_results = {
                            "auditados": auditados,
                            "tabela_encaminhamentos": tabela_encaminhamentos,
                            "tabela_achados": tabela_achados,
                            "tabela_situacoes": tabela_situacoes,
                        }
                        st.session_state.audit_completed = True

            except Exception as e:
                st.error(f"Ocorreu um erro durante o processamento: {e}")
    # else:
    #     st.info("Por favor, carregue todos os arquivos Excel de entrada.")

    if st.session_state.audit_completed:
        st.success("Auditoria já concluída, pode ir para tela de visualização de resultados ou geração de relatórios!")

elif page == "1. Carregar resultado de auditoria": # Início da nova página
    st.title("Carregar Resultado de Auditoria")
    st.write("Esta seção permite carregar um resultado de auditoria previamente salvo (arquivo .pkl) para visualizar e baixar os resultados sem a necessidade de reprocessar os arquivos de entrada.")

    arquivo_resultado = st.file_uploader("Carregar arquivo de resultado da auditoria (.pkl)", type=["pkl"])

    if arquivo_resultado:
        if st.button("Carregar e exibir resultados"):
            try:
                with st.spinner("Carregando e processando resultado..."):
                    # Carrega o objeto 'auditados' do arquivo pkl
                    auditados = pickle.load(arquivo_resultado)

                    # Gera novamente as tabelas a partir dos dados carregados
                    tabela_encaminhamentos = gerar_tabela_encaminhamentos(auditados)
                    tabela_achados = gerar_tabela_achados(auditados)
                    tabela_situacoes = gerar_tabela_situacoes_inconformes(auditados)

                    # Atualiza o estado da sessão para refletir os dados carregados
                    st.session_state.audit_results = {
                        "auditados": auditados,
                        "tabela_encaminhamentos": tabela_encaminhamentos,
                        "tabela_achados": tabela_achados,
                        "tabela_situacoes": tabela_situacoes,
                    }
                    st.session_state.audit_completed = True
                    st.session_state.files_processed = True # Marca como processado para consistência
                    st.session_state.download_files = {} # Limpa arquivos de download antigos

                    st.success("Resultado da auditoria carregado com sucesso!")
                    # st.rerun() # Força o recarregamento para exibir os resultados
            except Exception as e:
                st.error(f"Ocorreu um erro ao carregar o arquivo: {e}")

    if st.session_state.audit_completed:
        st.success("Auditoria já concluída ou carregada, pode ir para tela de visualização de resultados ou geração de relatórios!")


elif page == "2. Visualizar resultado de auditoria": # Início da nova página
    st.title("Visualizar Resultado de Auditoria")
    st.write("Esta seção permite visualizar e baixar os resultados de auditoria já processada.")

    if st.session_state.audit_completed:
        results = st.session_state.audit_results

        # 3. Geração das saídas (tabelas, relatórios, etc.)
        st.header("Resultados Gerados")

        # Usando abas para organizar melhor a visualização
        tab_graficos, tab_tabelas = st.tabs(["📊 Visualizar Gráficos", "📄 Visualizar Tabelas"])

        with tab_graficos:
            st.subheader("Quantitativo de Auditados por Achado")
            df_achados = results["tabela_achados"]
            achados_counts = (df_achados == 'X').sum().sort_values(ascending=True)
            st.bar_chart(achados_counts, horizontal=True)

            # Coleta de dados para os gráficos seguintes
            all_situations = []
            all_encaminhamentos_texto = []
            all_encaminhamentos_tipo = []
            situations_per_auditado = {}
            achados_per_auditado = {}

            for sigla, auditado in results["auditados"].items():
                if auditado.foi_auditado:
                    # Coleta de situações
                    situacoes = auditado.get_situacoes_inconformes()
                    all_situations.extend(situacoes)
                    situations_per_auditado[sigla] = len(situacoes)

                    # Coleta de achados
                    achados_per_auditado[sigla] = len(auditado.get_nomes_achados())

                    # Coleta de encaminhamentos (texto e tipo)
                    for p in auditado.procedimentos_executados:
                        if p.achado:
                            for e in p.achado.encaminhamentos:
                                all_encaminhamentos_texto.append(e['encaminhamento'].strip())
                                all_encaminhamentos_tipo.append(e['tipo'].strip())

            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Distribuição por Tipo de Encaminhamento")
                if all_encaminhamentos_tipo:
                    tipo_counts = pd.Series(all_encaminhamentos_tipo).value_counts()
                    st.bar_chart(tipo_counts) # Gráfico de pizza é melhor, mas bar_chart é nativo e eficaz
                else:
                    st.info("Nenhum encaminhamento proposto.")

            with col2:
                st.subheader("Top 10 Encaminhamentos Mais Propostos")
                if all_encaminhamentos_texto:
                    # Ordena os valores para garantir que o gráfico seja exibido do maior para o menor
                    encaminhamentos_counts = pd.Series(all_encaminhamentos_texto).value_counts().nlargest(10).sort_values(ascending=False)
                    st.bar_chart(encaminhamentos_counts, sort=False)
                else:
                    st.info("Nenhum encaminhamento proposto.")

            st.subheader("Top 10 Situações Inconformes Mais Recorrentes")
            if all_situations:
                # Ordena os valores para garantir que o gráfico seja exibido do maior para o menor
                situations_counts = pd.Series(all_situations).value_counts().nlargest(10).sort_values(ascending=False)
                st.bar_chart(situations_counts, sort=False)
            else:
                st.info("Nenhuma situação inconforme encontrada.")

            st.subheader("Ranking de Auditados")
            if situations_per_auditado and achados_per_auditado:
                df_rank_situacoes = pd.DataFrame.from_dict(situations_per_auditado, orient='index', columns=['Qtd. Situações Inconformes'])
                df_rank_achados = pd.DataFrame.from_dict(achados_per_auditado, orient='index', columns=['Qtd. Achados Distintos'])
                df_rank_combined = df_rank_achados.join(df_rank_situacoes)
                df_rank_combined = df_rank_combined.sort_values(by=['Qtd. Achados Distintos', 'Qtd. Situações Inconformes'], ascending=False)
                st.dataframe(df_rank_combined)

        with tab_tabelas:
            st.subheader("Achados por Auditado")
            st.dataframe(results["tabela_achados"])

            st.subheader("Encaminhamentos por Auditado")
            st.dataframe(results["tabela_encaminhamentos"])

            st.subheader("Situações Inconformes por Auditado")
            st.dataframe(results["tabela_situacoes"])

        st.header("Baixar Resultados", divider="gray")

        # Gera os arquivos para download apenas uma vez e os armazena no estado da sessão
        if not st.session_state.download_files:
            with st.spinner("Gerando arquivos para download... Por favor, aguarde."):
                # 1. Arquivo Pickle
                pkl_buffer = io.BytesIO()
                pickle.dump(results["auditados"], pkl_buffer)
                st.session_state.download_files['pkl'] = pkl_buffer.getvalue()

                # 2. Arquivo Excel com tabelas
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    results["tabela_achados"].to_excel(writer, sheet_name='Achados por Auditado')
                    results["tabela_encaminhamentos"].to_excel(writer, sheet_name='Encaminhamentos por Auditado')
                    results["tabela_situacoes"].to_excel(writer, sheet_name='Situações Inconformes')
                st.session_state.download_files['excel'] = excel_buffer.getvalue()

                # 3. Arquivos DOCX individuais e ZIP
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_f:
                    st.session_state.download_files['docx'] = {}
                    for sigla, auditado in results["auditados"].items():
                        if auditado.foi_auditado:
                            doc = auditado.documenta_procedimentos()
                            bio = io.BytesIO()
                            doc.save(bio)
                            docx_bytes = bio.getvalue()
                            st.session_state.download_files['docx'][sigla] = docx_bytes
                            zip_f.writestr(f"{auditado.sigla} - Relatorio.docx", docx_bytes)
                st.session_state.download_files['zip'] = zip_buffer.getvalue()

        # Exibe os botões de download usando os arquivos armazenados no estado da sessão
        st.download_button(
            label="Baixar Objeto Auditados (.pkl)",
            data=st.session_state.download_files['pkl'],
            file_name="auditados.pkl",
            mime="application/octet-stream",
            key="download_pkl"
        )

        st.download_button(
            label="Baixar Todas as Tabelas (.xlsx)",
            data=st.session_state.download_files['excel'],
            file_name="tabelas_consolidadas_auditoria.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_all_tables"
        )

        with st.expander("Baixar Relatórios Individuais (.docx)"):
            for sigla, docx_bytes in st.session_state.download_files['docx'].items():
                st.download_button(label=f"Baixar Relatório {sigla}", data=docx_bytes, file_name=f"{sigla} - Relatorio.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"download_{sigla}")

        st.download_button(
            label="Baixar Todos os Relatórios (.zip)",
            data=st.session_state.download_files['zip'],
            file_name="relatorios_auditados.zip",
            mime="application/zip",
            key="download_zip"
        )
    else:
        st.info("Por favor, carregue e processe os arquivos da auditoria antes de visualizar os resultados.")


elif page == "3. Gerar Relatórios": # Início da página "Gerar Relatórios"
    st.title("Gerar Relatórios")
    st.write("Esta seção permitirá a geração de relatórios personalizados a partir dos dados de auditoria processados.")

    if st.session_state.audit_completed:
        results = st.session_state.audit_results
        auditados = results["auditados"]

        tab_individuais, tab_consolidado = st.tabs(["Relatórios Individuais", "Anexo de Evidências"])

        with tab_consolidado:
            st.subheader("Gerar Anexo de Evidências")
            if st.button("Gerar Anexo de Evidências"):
                with st.spinner("Gerando anexo..."):
                    contexto_anexo_evidencias = []
                    for auditado in auditados.values():
                        contexto_anexo_evidencias.append({
                            'sigla_orgao': auditado.sigla,
                            'nome_orgao': auditado.nome,
                            'achados': list(auditado.get_achados().values()),
                        })

                    base = DocxTemplate("docs/anexo-evidencias-base.docx")
                    contexto = {'dados': contexto_anexo_evidencias}
                    base.render(contexto)

                    bio = io.BytesIO()
                    base.save(bio)
                    docx_bytes = bio.getvalue()
                    st.session_state.download_files['relatorio_evidencias'] = docx_bytes

            if 'relatorio_evidencias' in st.session_state.download_files:
                st.download_button(
                    label="Baixar Anexo de Evidências",
                    data=st.session_state.download_files['relatorio_evidencias'],
                    file_name="ANXX - Evidências.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="download_relatorio_evidencias"
                )

        with tab_individuais:
            st.subheader("Gerar Relatórios Individuais")

            st.info("Unidades auditadas e achados encontrados na auditoria.")
            col1, col2 = st.columns(2)
            with col1:
                st.write("Auditados:")
                df_auditados = pd.DataFrame([{'sigla': auditado.sigla, 'nome': auditado.nome} for auditado in auditados.values()]).set_index('sigla')
                st.dataframe(df_auditados, height=200)
            with col2:
                st.write("Achados:")
                df_achados_encontrados = pd.DataFrame([{'nome': nome_achado} for nome_achado in gerar_tabela_achados(auditados).columns])
                st.dataframe(df_achados_encontrados, height=200)

            st.subheader("1. Forneça dados de contexto adicionais (Opcional)")
            arquivo_contexto = st.file_uploader("Carregar Planilha de Contexto (.xlsx)", type=["xlsx"], help="A planilha deve ter uma coluna 'sigla' para identificar o auditado e as demais colunas com os dados de contexto.")
            df_contexto_extra = None
            if arquivo_contexto:
                df_contexto_extra = pd.read_excel(arquivo_contexto).set_index('sigla')
                st.write("Planilha de contexto carregadas:")
                st.dataframe(df_contexto_extra.head())

            arquivos_fontes_contexto = st.file_uploader("Arquivos presentes na planilha de contexto", accept_multiple_files=True)

            st.subheader("2. Forneça o template do relatório")
            template_md_content = st.text_area("Cole o template Markdown/Jinja2 aqui", height=250)
            st.write("Ou")
            arquivo_template_md = st.file_uploader("Carregue um arquivo de template (.md)", type=["md"])

            if arquivo_template_md:
                template_md_content = arquivo_template_md.read().decode('utf-8')
                st.text_area("Conteúdo do template carregado:", template_md_content, height=250, disabled=True)

            if template_md_content:
                vars_template = get_variaveis_template(template_md_content)
                st.write("Variáveis encontradas no template:")
                st.code(f"{vars_template}")

            st.subheader("3. Gere os relatórios")
            if st.button("Gerar Relatórios Individuais"):
                if not template_md_content:
                    st.error("Por favor, forneça um template (colando o texto ou carregando o arquivo .md).")
                else:
                    with st.spinner("Gerando relatórios individuais..."):
                        # Usar StrictUndefined para lançar erro se uma variável não for encontrada
                        env = Environment(loader=BaseLoader(), undefined=StrictUndefined)
                        template_relatorio_individual_docx = 'docs/template-relatorio-individual.docx'

                        generation_log = st.expander("Log de Geração", expanded=True)
                        zip_buffer_individuais = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer_individuais, 'w', zipfile.ZIP_DEFLATED) as zip_f:
                            for sigla, row_auditado in df_auditados.iterrows():
                                with generation_log:
                                    st.markdown(f"--- \n#### Processando: **{sigla}**")
                                    d_contexto_auditado = row_auditado.to_dict()
                                    d_contexto_auditado['sigla'] = sigla

                                    if df_contexto_extra is not None and sigla in df_contexto_extra.index:
                                        contexto_extra_auditado = df_contexto_extra.loc[sigla].to_dict()
                                        d_contexto_auditado.update(contexto_extra_auditado)

                                    # Adiciona o objeto auditado inteiro ao contexto. Mais simples e flexível!
                                    d_contexto_auditado['auditado'] = auditados[sigla]

                                    try:
                                        template = env.from_string(template_md_content)
                                        conteudo_final_md = template.render(d_contexto_auditado)

                                        # Checagem de variáveis (opcional, mas útil para debug)
                                        vars_contexto = set(d_contexto_auditado.keys())
                                        vars_faltando = vars_template - vars_contexto
                                        vars_nao_utilizadas = vars_contexto - vars_template

                                        if len(vars_faltando):
                                            st.info(f"**Variáveis de contexto não utilizadas:** As seguintes variáveis dos dados não foram usadas no template: `{vars_nao_utilizadas}`")

                                    except jinja2.exceptions.UndefinedError as e:
                                        st.error(f"**Erro no template para `{sigla}`:** A variável `{e.message.split(' is undefined')[0]}` não foi encontrada.")
                                        st.error("Verifique se o nome da variável está correto no template e se ela foi fornecida nos dados de contexto.")
                                        # Pula para o próximo auditado
                                        continue

                                    # Salva MD temporariamente
                                    md_filename = f'tmp/relatorio-individual-{sigla}.md'
                                    with open(md_filename, 'w', encoding='utf-8') as f:
                                        f.write(conteudo_final_md)

                                    # Converte para DOCX
                                    docx_filename = f'tmp/relatorio-individual-{sigla}.docx'
                                    args_docx = ['--reference-doc=' + template_relatorio_individual_docx, '--figure-caption-position=above', '--filter=pandoc-crossref']

                                    # Configura o logger para capturar avisos do pypandoc
                                    pypandoc_logger = logging.getLogger('pypandoc')
                                    pypandoc_logger.setLevel(logging.WARNING)
                                    log_container = st.empty()
                                    handler = StreamlitLogHandler(log_container)
                                    pypandoc_logger.addHandler(handler)

                                    try:
                                        output = pypandoc.convert_file(md_filename, to='docx', outputfile=docx_filename, extra_args=args_docx)
                                        assert output == ""
                                        if not handler.records: # Se não houve warnings
                                            st.success(f"Relatório para **{sigla}** gerado com sucesso.")
                                    except Exception as e:
                                        st.error(f"Erro ao gerar relatório para **{sigla}**: {e}")
                                    finally:
                                        pypandoc_logger.removeHandler(handler)


                                    # Adiciona os arquivos .md e .docx ao ZIP
                                    zip_f.write(docx_filename, arcname=f'Relatorio-{sigla}.docx')
                                    zip_f.write(md_filename, arcname=f'Relatorio-{sigla}.md')

                        st.session_state.download_files['relatorios_individuais_zip'] = zip_buffer_individuais.getvalue()
                        st.success("Relatórios individuais gerados e compactados com sucesso!")

            if 'relatorios_individuais_zip' in st.session_state.download_files:
                st.download_button(
                    label="Baixar Todos os Relatórios Individuais (.zip)",
                    data=st.session_state.download_files['relatorios_individuais_zip'],
                    file_name="relatorios_individuais.zip",
                    mime="application/zip",
                    key="download_individuais_zip"
                )

    else:
        st.info("Por favor, carregue e processe os arquivos da auditoria antes de gerar relatórios.")
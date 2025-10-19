import streamlit as st
import pandas as pd
import re
import os
import io
import pickle
import zipfile

from classes import FonteInformacao, Achado, AcaoVerificacao, ProcedimentoAuditoria, Auditado, \
    gerar_tabela_encaminhamentos, gerar_tabela_achados, gerar_tabela_situacoes_inconformes

# Funções auxiliares para carregar os dados dos arquivos Excel
def carregar_dados(filepath, sheet_name=0, skiprows=2):
    try:
        return pd.read_excel(filepath, sheet_name=sheet_name, skiprows=skiprows).map(lambda x: x.strip() if isinstance(x, str) else x)
    except Exception as e:
        st.error(f"Erro ao carregar a planilha '{sheet_name}': {e}")
        return None

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
page = st.sidebar.radio("Navegação", ["Aplicar Procedimentos de Auditoria", "Carregar resultado de auditoria", "Gerar Relatórios"])

if page == "Aplicar Procedimentos de Auditoria": # Início da página "Aplicar Procedimentos de Auditoria"
    st.title("Aplicar Procedimentos de Auditoria")
    st.write("Esta seção realiza a aplicação dos procedimentos de auditoria definidos no mapa de verificação de achados. O processo gera como saída o objeto no modelo de dados do Audita, planilhas apresentando relação achados, encaminhamentos e situações encontrados por auditado, e relatórios individuais da aplicação dos procedimentos nos auditados.")

    with st.expander("Modelo de Dados do Audita"):
        st.image('mermaid-diagram.png')

    # 1. Upload dos arquivos Excel
    with st.expander("1. Carregar Arquivos Excel", expanded=True):
        arquivo_auditados = st.file_uploader("Base de Auditados (ex: base-auditados.xlsx)", type=["xlsx"])
        arquivo_mapa_achados  = st.file_uploader("Mapa de Verificação e Achados (ex: mapa-verificacao-achados.xlsx)", type=["xlsx"])
        arquivos_fontes_dados = st.file_uploader("Fontes de Informação (arquivos .xlsx)", type=["xlsx"], accept_multiple_files=True)

    # 2. Processamento dos dados

    if arquivo_auditados and arquivo_mapa_achados and arquivos_fontes_dados:
        if st.button("Processar arquivos e gerar achados"):
            # st.header("2. Processando Dados e Gerando Resultados")
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
                        tabela_encaminhamentos = gerar_tabela_encaminhamentos(auditados, procedimentos)
                        tabela_achados = gerar_tabela_achados(auditados, procedimentos)
                        tabela_situacoes = gerar_tabela_situacoes_inconformes(auditados, procedimentos)

                        st.session_state.audit_results = {
                            "auditados": auditados,
                            "tabela_encaminhamentos": tabela_encaminhamentos,
                            "tabela_achados": tabela_achados,
                            "tabela_situacoes": tabela_situacoes,
                        }
                        st.session_state.audit_completed = True
                        st.success("Auditoria concluída!")

            except Exception as e:
                st.error(f"Ocorreu um erro durante o processamento: {e}")
    else:
        st.info("Por favor, carregue todos os arquivos Excel de entrada.")

    if st.session_state.audit_completed:
        results = st.session_state.audit_results

        # 3. Geração das saídas (tabelas, relatórios, etc.)
        st.header("Resultados Gerados", divider="gray")

        with st.expander("Visualizar Tabelas de Resultados"):
            st.subheader("Encaminhamentos por Auditado")
            st.dataframe(results["tabela_encaminhamentos"])

            st.subheader("Achados por Auditado")
            st.dataframe(results["tabela_achados"])

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

elif page == "Carregar resultado de auditoria": # Início da nova página
    st.title("Carregar Resultado de Auditoria")
    st.write("Esta seção permite carregar um resultado de auditoria previamente salvo (arquivo .pkl) para visualizar e baixar os resultados sem a necessidade de reprocessar os arquivos de entrada.")

    arquivo_resultado = st.file_uploader("Carregar arquivo de resultado da auditoria (.pkl)", type=["pkl"])

    if arquivo_resultado:
        if st.button("Carregar e exibir resultados"):
            try:
                with st.spinner("Carregando e processando resultado..."):
                    # Carrega o objeto 'auditados' do arquivo pkl
                    auditados = pickle.load(arquivo_resultado)

                    # Reconstrói o dicionário de procedimentos a partir dos achados em cada auditado
                    procedimentos = {}
                    for auditado in auditados.values():
                        for achado in auditado.achados:
                            if achado.procedimento.id not in procedimentos:
                                procedimentos[achado.procedimento.id] = achado.procedimento

                    # Gera novamente as tabelas a partir dos dados carregados
                    tabela_encaminhamentos = gerar_tabela_encaminhamentos(auditados, procedimentos)
                    tabela_achados = gerar_tabela_achados(auditados, procedimentos)
                    tabela_situacoes = gerar_tabela_situacoes_inconformes(auditados, procedimentos)

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
                    st.rerun() # Força o recarregamento para exibir os resultados
            except Exception as e:
                st.error(f"Ocorreu um erro ao carregar o arquivo: {e}")

elif page == "Gerar Relatórios": # Início da página "Gerar Relatórios"
    st.title("Gerar Relatórios")
    st.info("Funcionalidade para gerar relatórios consolidados a ser implementada.")
    st.write("Esta seção permitirá a geração de relatórios personalizados a partir dos dados de auditoria processados.")

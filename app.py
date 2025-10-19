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
        return pd.read_excel(filepath, sheet_name=sheet_name, skiprows=skiprows).applymap(lambda x: x.strip() if isinstance(x, str) else x)
    except Exception as e:
        st.error(f"Erro ao carregar a planilha '{sheet_name}': {e}")
        return None

# Inicializa o estado da sessão para manter os resultados após o download
if 'audit_completed' not in st.session_state:
    st.session_state.audit_completed = False
    st.session_state.audit_results = None

if 'files_processed' not in st.session_state:
    st.session_state.files_processed = False

st.sidebar.title("Argos - Auditoria Simplificada")
page = st.sidebar.radio("Navegação", ["Gerar achados", "Gerar Relatórios"])

if page == "Gerar achados":
    st.title("Gerar Achados de Auditoria")

    # 1. Upload dos arquivos Excel
    with st.expander("1. Carregar Arquivos Excel", expanded=True):
        arquivo_auditados = st.file_uploader("Base de Auditados (ex: base-auditados.xlsx)", type=["xlsx"])
        arquivo_mapa_achados  = st.file_uploader("Mapa de Verificação e Achados (ex: mapa-verificacao-achados.xlsx)", type=["xlsx"])
        arquivos_fontes_dados = st.file_uploader("Fontes de Informação (arquivos .xlsx)", type=["xlsx"], accept_multiple_files=True)

    # 2. Processamento dos dados
    st.header("2. Processar Dados e Gerar Resultados")
    if arquivo_auditados and arquivo_mapa_achados and arquivos_fontes_dados:
        try:
            # Leitura dos DataFrames
            with st.spinner("Carregando planilhas..."):
        if st.button("Processar arquivos e gerar achados"):
            st.session_state.files_processed = True
            st.session_state.audit_completed = False
            st.session_state.audit_results = None

    if st.session_state.files_processed:
        st.header("2. Processamento e Geração de Achados")
        with st.spinner("Processando arquivos e executando auditoria... Por favor, aguarde."):
            try:
                # Leitura dos DataFrames
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
                fontes_dados_carregadas = {f.name: f for f in arquivos_fontes_dados}

            # 1. Leitura das fontes de informação
            with st.spinner("Processando fontes de informação..."):
                # 1. Leitura das fontes de informação
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
                        fontes[fonte.id] = fonte
                    except (IOError, AttributeError):
                        st.error(f"Arquivo da fonte de informação '{fonte.descricao}' ('{nome_arquivo_fonte}') não foi encontrado ou não pôde ser lido. Verifique se o arquivo foi carregado e se o nome corresponde ao da planilha 'Fontes de Informação'.")

            # 2. Leitura das ações de verificação
            with st.spinner("Processando ações de verificação..."):
                # 2. Leitura das ações de verificação
                acoes = {}
                for _, row in df_acoes_verificacao.iterrows():
                    fonte_informacao = fontes.get(row['id_fonte_informacao'])
                    if not fonte_informacao:
                        st.error(f"Ação de verificação '{row['id']}' refere-se a uma fonte de informação ('{row['id_fonte_informacao']}') que não foi encontrada. Verifique a planilha 'Ações de Verificação'.")
                        # st.stop()

                        st.warning(f"Ação de verificação '{row['id']}' refere-se a uma fonte de informação ('{row['id_fonte_informacao']}') que não foi encontrada. Esta ação será ignorada.")
                        continue
                    acao = AcaoVerificacao(
                        fonte_informacao=fonte_informacao,
                        informacao_requerida=row['informacao_requerida'],

                        acao_exclusiva_auditados=row['acao_exclusiva_auditados'],
                        criterio=row['criterio'],
                        fonte_informacao=fonte_informacao, informacao_requerida=row['informacao_requerida'],
                        acao_exclusiva_auditados=row['acao_exclusiva_auditados'], criterio=row['criterio'],
                        descricao_situacao_inconforme=row['descricao_situacao_inconforme'],

                        descricao_evidencia=row['descricao_evidencia'],
                        situacao_inconforme=row['situacao_inconforme'],
                        descricao_evidencia=row['descricao_evidencia'], situacao_inconforme=row['situacao_inconforme'],
                        situacao_encontrada_nan_e_achado=row['situacao_encontrada_nan_e_achado'],
                        tipo_encaminhamento=row['tipo_encaminhamento'],
                        encaminhamento=row['encaminhamento'],
                        tipo_encaminhamento=row['tipo_encaminhamento'], encaminhamento=row['encaminhamento'],
                        pre_encaminhamento=row['pre_encaminhamento'],
                        auditado_inexistente_e_achado=row['auditado_inexistente_e_achado'],
                        descricao_auditado_inexistente=row['descricao_auditado_inexistente'],
                        id=row['id']
                        descricao_auditado_inexistente=row['descricao_auditado_inexistente'], id=row['id']
                    )
                    acoes[acao.id] = acao  # Armazena no dicionário para referência posterior
                    acoes[acao.id] = acao

            # 3. Leitura dos procedimentos de auditoria
            with st.spinner("Processando procedimentos de auditoria..."):
                # 3. Leitura dos procedimentos de auditoria
                procedimentos = {}
                for _, row in df_procedimentos.iterrows():
                    procedimento = ProcedimentoAuditoria(
                        descricao=row['descricao'],
                        logica_achado=row['logica_achado'],
                        numero_achado=row['numero_achado'],
                        nome_achado=row['nome_achado'],
                        id=row['id']
                        descricao=row['descricao'], logica_achado=row['logica_achado'],
                        numero_achado=row['numero_achado'], nome_achado=row['nome_achado'], id=row['id']
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
                # 4. Leitura dos auditados
                auditados = {}
                for _, row in df_jurisdicionados.iterrows():
                    auditado = Auditado(
                        nome=row['orgao'],
                        sigla=row['sigla'],
                        # id=row['id']
                    )
                    auditado = Auditado(nome=row['orgao'], sigla=row['sigla'])
                    auditados[auditado.sigla] = auditado

            st.success("Arquivos carregados e processados com sucesso! Pronto para iniciar a auditoria.")
                # Execução da auditoria
                for auditado in auditados.values():
                    auditado.aplicar_procedimentos(procedimentos.values(), debug=False)

            # Botão para iniciar a auditoria
            if st.button("Iniciar Auditoria"):
                st.session_state.audit_completed = False
                with st.spinner("Executando procedimentos de auditoria... Por favor, aguarde."):
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

            except Exception as e:
                st.error(f"Ocorreu um erro durante o processamento: {e}")
                st.session_state.files_processed = False # Reseta para permitir nova tentativa

    if st.session_state.audit_completed:
        st.success("Auditoria concluída com sucesso!")
        results = st.session_state.audit_results

        st.header("3. Resultados Gerados")

        with st.expander("Visualizar Tabelas de Resultados"):
            st.subheader("Encaminhamentos por Auditado")
            st.dataframe(results["tabela_encaminhamentos"])

            st.subheader("Achados por Auditado")
            st.dataframe(results["tabela_achados"])

            st.subheader("Situações Inconformes por Auditado")
            st.dataframe(results["tabela_situacoes"])

        # Download do objeto auditados em pickle
        pkl_buffer = io.BytesIO()
        pickle.dump(results["auditados"], pkl_buffer)
        pkl_buffer.seek(0)
        st.download_button(
            label="Baixar Objeto Auditados (.pkl)",
            data=pkl_buffer,
            file_name="auditados.pkl",
            mime="application/octet-stream",
            key="download_pkl"
        )

        # Botão para baixar todas as tabelas em um único arquivo Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
            results["tabela_achados"].to_excel(writer, sheet_name='Achados por Auditado')
            results["tabela_encaminhamentos"].to_excel(writer, sheet_name='Encaminhamentos por Auditado')
            results["tabela_situacoes"].to_excel(writer, sheet_name='Situações Inconformes')

        excel_buffer.seek(0)

        st.download_button(
            label="Baixar Todas as Tabelas (.xlsx)",
            data=excel_buffer,
            file_name="tabelas_consolidadas_auditoria.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_all_tables"
        )

        # Download de todos os relatórios em um arquivo zip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_f:
            with st.expander("Baixar Relatórios Individuais (.docx)"):
                for sigla, auditado in results["auditados"].items():
                    if auditado.foi_auditado:
                        doc = auditado.documenta_procedimentos()
                        bio = io.BytesIO()
                        doc.save(bio)

                        st.download_button(label=f"Baixar Relatório {sigla}", data=bio.getvalue(), file_name=f"{sigla} - Relatorio.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"download_{sigla}")
                        zip_f.writestr(f"{auditado.sigla} - Relatorio.docx", bio.getvalue())

        st.download_button(
            label="Baixar Todos os Relatórios (.zip)",
            data=zip_buffer.getvalue(),
            file_name="relatorios_auditados.zip",
            mime="application/zip",
            key="download_zip"
        )

    elif not (arquivo_auditados and arquivo_mapa_achados and arquivos_fontes_dados):
        st.warning("Por favor, carregue todos os arquivos na seção 1 para continuar.")

elif page == "Gerar Relatórios":
    st.title("Gerar Relatórios")
    st.info("Funcionalidade para gerar relatórios consolidados a ser implementada.")
    st.write("Esta seção permitirá a geração de relatórios personalizados a partir dos dados de auditoria processados.")
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

                # st.rerun()

            if st.session_state.audit_completed:
                st.success("Auditoria concluída!")
                results = st.session_state.audit_results
                # 3. Geração das saídas (tabelas, relatórios, etc.)
                st.header("3. Resultados Gerados")

                with st.expander("Visualizar Tabelas de Resultados"):
                    st.subheader("Encaminhamentos por Auditado")
                    st.dataframe(results["tabela_encaminhamentos"])

                    st.subheader("Achados por Auditado")
                    st.dataframe(results["tabela_achados"])

                    st.subheader("Situações Inconformes por Auditado")
                    st.dataframe(results["tabela_situacoes"])

                st.header("4. Baixar Resultados")

                # Download do objeto auditados em pickle
                pkl_buffer = io.BytesIO()
                pickle.dump(results["auditados"], pkl_buffer)
                pkl_buffer.seek(0)
                st.download_button(
                    label="Baixar Objeto Auditados (.pkl)",
                    data=pkl_buffer,
                    file_name="auditados.pkl",
                    mime="application/octet-stream",
                    key="download_pkl"
                )

                # Botão para baixar todas as tabelas em um único arquivo Excel
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                    results["tabela_achados"].to_excel(writer, sheet_name='Achados por Auditado')
                    results["tabela_encaminhamentos"].to_excel(writer, sheet_name='Encaminhamentos por Auditado')
                    results["tabela_situacoes"].to_excel(writer, sheet_name='Situações Inconformes')

                excel_buffer.seek(0)

                st.download_button(
                    label="Baixar Todas as Tabelas (.xlsx)",
                    data=excel_buffer,
                    file_name="tabelas_consolidadas_auditoria.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_all_tables"
                )

                # Download de todos os relatórios em um arquivo zip
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_f:
                    with st.expander("Baixar Relatórios Individuais (.docx)"):
                        for sigla, auditado in results["auditados"].items():
                            if auditado.foi_auditado:
                                doc = auditado.documenta_procedimentos()
                                bio = io.BytesIO()
                                doc.save(bio)

                                st.download_button(label=f"Baixar Relatório {sigla}", data=bio.getvalue(), file_name=f"{sigla} - Relatorio.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"download_{sigla}")
                                zip_f.writestr(f"{auditado.sigla} - Relatorio.docx", bio.getvalue())

                st.download_button(
                    label="Baixar Todos os Relatórios (.zip)",
                    data=zip_buffer.getvalue(),
                    file_name="relatorios_auditados.zip",
                    mime="application/zip",
                    key="download_zip"
                )

                # with st.expander("Baixar Relatórios Individuais (.docx)"):
                #     for sigla, auditado in results["auditados"].items():
                #         if auditado.foi_auditado:
                #             doc = auditado.documenta_procedimentos()
                #             bio = io.BytesIO()
                #             doc.save(bio)
                #             st.download_button(label=f"Baixar Relatório {sigla}", data=bio.getvalue(), file_name=f"{sigla} - Relatorio.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"download_{sigla}")

        except Exception as e:
            st.error(f"Ocorreu um erro durante o processamento: {e}")
    else:
        st.warning("Por favor, carregue todos os arquivos Excel.")

elif page == "Gerar Relatórios":
    st.title("Gerar Relatórios")
    st.info("Funcionalidade para gerar relatórios consolidados a ser implementada.")
    st.write("Esta seção permitirá a geração de relatórios personalizados a partir dos dados de auditoria processados.")

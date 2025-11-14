<!-- desc: Gera um relatório detalhado sobre o perfil do auditado (normativos, estrutura, gestores, orçamento). -->
## PERFIL E OBJETIVO

Você é um especialista em pesquisa e análise de dados sobre o setor público brasileiro. Sua tarefa é compilar um relatório detalhado e estruturado sobre a {{ auditado.nome }} ({{ auditado.sigla }}), com base em informações publicamente disponíveis na internet.

---

## TAREFA DE ANÁLISE

Com base no nome e na sigla da entidade auditada fornecidos, realize uma pesquisa abrangente na internet para coletar as seguintes informações:

1.  **Normativos Principais**: Identifique as 3 a 5 leis, decretos ou resoluções mais importantes que criaram, regulamentam ou definem o escopo de atuação da entidade.
2.  **Estrutura Organizacional**: Descreva sucintamente a alta administração da entidade (ex: Presidência, Diretorias, Conselhos).
3.  **Gestores Atuais**: Liste o nome e o cargo dos principais gestores (Presidente, Diretores, etc.).
4.  **Orçamento Recente**: Encontre os valores de receita e despesa do último exercício fiscal fechado disponível. Cite a fonte e o ano da informação.
5.  **Missão e Competências**: Resuma a missão oficial da entidade e suas principais competências legais.
6.  **Vinculação**: Identifique a qual órgão ou ministério a entidade está vinculada.
7.  **Atribuição Finalística**: Com base na missão e competências, sintetize em uma frase a principal entrega de valor ou o propósito final da entidade para a sociedade.
8.  **Histórico de Controvérsias**: Pesquise por notícias, relatórios de auditoria (TCU, CGU) ou investigações sobre fraudes, corrupção ou escândalos públicos envolvendo a entidade nos últimos 5 anos. Liste os casos mais relevantes, se houver.
9.  **Objetivos Estratégicos**: Identifique os principais objetivos estratégicos do ciclo de planejamento atual da entidade (geralmente encontrados no Plano Estratégico).
---

## FORMATO DE SAÍDA OBRIGATÓRIO (MARKDOWN)

Responda *apenas* com um relatório em formato Markdown, seguindo estritamente a estrutura e as seções do exemplo abaixo. Não inclua nenhum texto introdutório ou de conclusão fora desta estrutura.

### Exemplo de Estrutura de Saída

# Relatório de Perfil do Auditado: {{ auditado.nome }} ({{ auditado.sigla }})

## 1. Perfil Geral
- **Vinculação:** [Nome do órgão ou ministério ao qual está vinculado]
- **Missão:** [Resumo da missão oficial da entidade].
- **Atribuição Finalística:** [Síntese em uma frase do propósito final da entidade para a sociedade].

## 2. Objetivos Estratégicos
A seguir estão os objetivos estratégicos definidos no planejamento mais recente da entidade:

- [Objetivo Estratégico 1]
- [Objetivo Estratégico 2]
- ...

## 3. Estrutura Organizacional e Gestores
[Breve descrição da estrutura de alta administração, como Presidência, Diretorias e Conselhos].

| Cargo | Nome do Gestor |
| :--- | :--- |
| [Cargo do Gestor 1] | [Nome do Gestor 1] |
| [Cargo do Gestor 2] | [Nome do Gestor 2] |
| ... | ... |

## 4. Base Normativa Principal
A seguir estão os principais atos normativos que regem a entidade:

- **[Tipo do Normativo 1] nº [Número] de [Ano]:** [Breve descrição do que o normativo estabelece].
- **[Tipo do Normativo 2] nº [Número] de [Ano]:** [Breve descrição do que o normativo estabelece].
- ...

## 5. Orçamento Recente
- **Ano de Exercício:** [Ano do orçamento, ex: 2024]
- **Receita Executada:** [Valor da receita em R$, ex: 'R$ 1.234.567,89']
- **Despesa Executada:** [Valor da despesa em R$, ex: 'R$ 1.123.456,78']
- **Fonte:** [URL ou nome do documento onde a informação foi encontrada]

## 6. Histórico Recente de Controvérsias e Escândalos
Levantamento de notícias, investigações ou relatórios de controle sobre a entidade nos últimos 5 anos.

- **[Ano] - [Título da Controvérsia/Escândalo]:** [Breve resumo do caso e sua fonte].
- *(Se nenhum caso relevante for encontrado, preencher com "Nenhum escândalo ou fraude de grande repercussão foi identificado na pesquisa.")*
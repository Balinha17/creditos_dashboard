from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Análise Crédito Educativo",
    page_icon="🎓",
    layout="wide",
)

# =========================
# CONFIG
# =========================

PASTA_APP = Path(__file__).resolve().parent

# Pesos do score. Dá para ajustar depois.
PESO_PERCENTUAL = 0.45
PESO_SALDO = 0.25
PESO_GAP_DILATACAO = 8
ALERTA_POS_DILATACAO_NEGATIVO = 20
ALERTA_POS_DILATACAO_ZERO_OU_UM = 10
ALERTA_SEMESTRES_RESTANTES_ZERO = 15
ALERTA_SEMESTRES_RESTANTES_UM = 5


# =========================
# FUNÇÕES AUXILIARES
# =========================

def localizar_excel():
    arquivos = sorted(PASTA_APP.glob("*.xlsx"))
    if not arquivos:
        return None
    # Se houver mais de um, pega o mais recente.
    return max(arquivos, key=lambda p: p.stat().st_mtime)


def limpar_numero(valor):
    if pd.isna(valor):
        return np.nan

    if isinstance(valor, (int, float, np.number)):
        return float(valor)

    texto = str(valor).strip()
    texto = texto.replace("R$", "").replace("%", "").replace(" ", "")

    # pt-BR: 1.234,56
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except Exception:
        return np.nan


def normalizar_colunas(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def achar_coluna(df, opcoes):
    colunas = list(df.columns)
    mapa = {c.lower().strip(): c for c in colunas}

    for nome in opcoes:
        chave = nome.lower().strip()
        if chave in mapa:
            return mapa[chave]

    for c in colunas:
        c_low = c.lower().strip()
        for nome in opcoes:
            if nome.lower().strip() in c_low:
                return c

    return None


def classificar_faixa(score):
    if score >= 75:
        return "Crítico"
    if score >= 55:
        return "Alto"
    if score >= 35:
        return "Médio"
    return "Baixo"


def explicar_motivo(row):
    motivos = []

    if row["Percentual Conclusão"] < 60:
        motivos.append("conclusão muito baixa")
    elif row["Percentual Conclusão"] < 70:
        motivos.append("baixo percentual de conclusão")

    if row["Semestres utilizados pós dilatação"] < 0:
        motivos.append("já ultrapassou a dilatação")
    elif row["Semestres utilizados pós dilatação"] <= 1:
        motivos.append("sem margem de semestres")

    if row["Semestres restantes"] <= 0:
        motivos.append("semestres restantes zerados")
    elif row["Semestres restantes"] == 1:
        motivos.append("apenas 1 semestre restante")

    if row["Saldo Normalizado"] >= 70:
        motivos.append("saldo devedor alto frente à base")

    return ", ".join(motivos) if motivos else "acompanhar"


def formatar_moeda(valor):
    if pd.isna(valor):
        valor = 0
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def preparar_score(out):
    max_saldo = out["Saldo devedor"].max()
    out["Saldo Normalizado"] = np.where(max_saldo > 0, out["Saldo devedor"] / max_saldo * 100, 0)

    out["Gap Dilatação"] = out["Semestres utilizados pós dilatação"].apply(
        lambda x: abs(x) if pd.notna(x) and x < 0 else 0
    )

    out["Alerta Semestre"] = out["Semestres utilizados pós dilatação"].apply(
        lambda x: ALERTA_POS_DILATACAO_NEGATIVO
        if pd.notna(x) and x < 0
        else ALERTA_POS_DILATACAO_ZERO_OU_UM
        if pd.notna(x) and x <= 1
        else 0
    )

    out["Alerta Restante"] = out["Semestres restantes"].apply(
        lambda x: ALERTA_SEMESTRES_RESTANTES_ZERO
        if pd.notna(x) and x <= 0
        else ALERTA_SEMESTRES_RESTANTES_UM
        if pd.notna(x) and x == 1
        else 0
    )

    out["Score Criticidade"] = (
        ((100 - out["Percentual Conclusão"]) * PESO_PERCENTUAL)
        + (out["Saldo Normalizado"] * PESO_SALDO)
        + (out["Gap Dilatação"] * PESO_GAP_DILATACAO)
        + out["Alerta Semestre"]
        + out["Alerta Restante"]
    ).clip(0, 100)

    out["Faixa de Risco"] = out["Score Criticidade"].apply(classificar_faixa)
    out["Motivo"] = out.apply(explicar_motivo, axis=1)

    return out


@st.cache_data
def carregar_dados(uploaded_file):
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
        origem = uploaded_file.name
    else:
        caminho = localizar_excel()
        if caminho is None:
            st.error("Não encontrei nenhum arquivo .xlsx na pasta do app.")
            st.stop()
        df = pd.read_excel(caminho)
        origem = caminho.name

    df = normalizar_colunas(df)

    col_matricula = achar_coluna(df, ["MATRICULA", "Matrícula"])
    col_nome = achar_coluna(df, ["NOME", "Nome"])
    col_credito = achar_coluna(df, ["CREDITO", "Crédito"])
    col_curso_original = achar_coluna(df, ["NOCURSO", "Curso"])
    col_curso_tratado = achar_coluna(df, ["Curso tratado", "Curso Tratado", "curso_tratado"])
    col_situacao = achar_coluna(df, ["Situação", "Situacao"])
    col_percentual = achar_coluna(df, ["Percentual %", "Percentual", "%"])
    col_saldo = achar_coluna(df, ["Saldo devedor", "Saldo"])
    col_pos_dilatacao = achar_coluna(df, ["Semestres utilizados pós dilatação", "pos dilatacao", "pós dilatação"])
    col_restantes = achar_coluna(df, ["Semestres restantes", "restantes"])
    col_previsao = achar_coluna(df, ["PREVISÃO DE FORMATURA ANO/SEMESTRE", "previsão de formatura", "previsao de formatura"])
    col_sem_matriz = achar_coluna(df, ["Semestres Matriz Curricular", "matriz curricular"])
    col_sem_util = achar_coluna(df, ["Semestres de Utilização em Nº", "utilização em nº", "utilizacao"])
    col_sem_dilat = achar_coluna(df, ["Semestre com dilatação", "semestre com dilatacao"])

    obrigatorias = {
        "Nome": col_nome,
        "Curso original": col_curso_original,
        "Percentual": col_percentual,
        "Saldo devedor": col_saldo,
        "Semestres utilizados pós dilatação": col_pos_dilatacao,
        "Semestres restantes": col_restantes,
    }

    faltando = [k for k, v in obrigatorias.items() if v is None]
    if faltando:
        st.error(f"Não encontrei estas colunas: {', '.join(faltando)}")
        st.write("Colunas encontradas:", list(df.columns))
        st.stop()

    out = pd.DataFrame()
    out["Matrícula"] = df[col_matricula] if col_matricula else ""
    out["Nome"] = df[col_nome]
    out["Crédito"] = df[col_credito] if col_credito else ""
    out["Curso original"] = df[col_curso_original]

    # AQUI É A MELHORIA:
    # Se existir "Curso tratado", usa ela como curso principal.
    # Se estiver vazia em alguma linha, cai para o curso original.
    if col_curso_tratado:
        out["Curso tratado"] = df[col_curso_tratado].fillna("").astype(str).str.strip()
        out["Curso"] = np.where(
            out["Curso tratado"].str.len() > 0,
            out["Curso tratado"],
            out["Curso original"],
        )
    else:
        out["Curso tratado"] = ""
        out["Curso"] = out["Curso original"]

    out["Situação"] = df[col_situacao] if col_situacao else ""
    out["Percentual Conclusão"] = df[col_percentual].apply(limpar_numero)
    out["Saldo devedor"] = df[col_saldo].apply(limpar_numero)
    out["Semestres utilizados pós dilatação"] = df[col_pos_dilatacao].apply(limpar_numero)
    out["Semestres restantes"] = df[col_restantes].apply(limpar_numero)
    out["Previsão formatura"] = df[col_previsao] if col_previsao else ""
    out["Semestres matriz"] = df[col_sem_matriz].apply(limpar_numero) if col_sem_matriz else np.nan
    out["Semestres utilizados"] = df[col_sem_util].apply(limpar_numero) if col_sem_util else np.nan
    out["Semestre com dilatação"] = df[col_sem_dilat].apply(limpar_numero) if col_sem_dilat else np.nan

    out = out.dropna(subset=["Percentual Conclusão", "Saldo devedor"]).copy()
    out = preparar_score(out)

    return out, origem, bool(col_curso_tratado)


# =========================
# APP
# =========================

st.title("🎓 Análise de Crédito Educativo")
st.caption("Alunos com crédito educativo, conclusão abaixo de 85% e prazo de concessão encerrando em 2026/1")

with st.sidebar:
    st.header("Arquivo")
    uploaded_file = st.file_uploader("Enviar outra planilha Excel", type=["xlsx"])
    st.caption("Se não enviar nada, o app usa automaticamente o arquivo .xlsx que estiver no GitHub.")

df, origem, tem_curso_tratado = carregar_dados(uploaded_file)

with st.sidebar:
    st.success(f"Arquivo carregado: {origem}")

    if tem_curso_tratado:
        st.info("Usando a coluna 'Curso tratado' para agrupar os cursos.")
    else:
        st.warning("Coluna 'Curso tratado' não encontrada. Agrupando por curso original.")

    st.header("Filtros")

    cursos_disponiveis = sorted(df["Curso"].dropna().unique())
    cursos = st.multiselect("Curso tratado", cursos_disponiveis, default=cursos_disponiveis)

    riscos = st.multiselect(
        "Faixa de risco",
        ["Crítico", "Alto", "Médio", "Baixo"],
        default=["Crítico", "Alto", "Médio", "Baixo"],
    )

    percentual_max = st.slider("Percentual máximo de conclusão", 0, 85, 85)
    saldo_min = st.number_input("Saldo mínimo", min_value=0.0, value=0.0, step=1000.0)

filtro = df[
    df["Curso"].isin(cursos)
    & df["Faixa de Risco"].isin(riscos)
    & (df["Percentual Conclusão"] <= percentual_max)
    & (df["Saldo devedor"] >= saldo_min)
].copy()

# =========================
# CARDS
# =========================

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Alunos filtrados", len(filtro))
col2.metric("Saldo total", formatar_moeda(filtro["Saldo devedor"].sum()))
col3.metric("Média conclusão", f"{filtro['Percentual Conclusão'].mean():.1f}%" if len(filtro) else "0%")
col4.metric("Casos críticos", len(filtro[filtro["Faixa de Risco"] == "Crítico"]))
col5.metric("Score médio", f"{filtro['Score Criticidade'].mean():.1f}" if len(filtro) else "0")

st.divider()

with st.expander("Como a classificação de risco é calculada"):
    st.markdown(
        f"""
O app calcula um **Score de Criticidade de 0 a 100**.

A fórmula atual é:

```text
Score =
(100 - Percentual de Conclusão) * {PESO_PERCENTUAL}
+ Saldo Normalizado * {PESO_SALDO}
+ Gap de Dilatação * {PESO_GAP_DILATACAO}
+ Alerta de Semestres Pós Dilatação
+ Alerta de Semestres Restantes
```

**Saldo Normalizado**: transforma o maior saldo da base em 100 e calcula os demais proporcionalmente.

**Gap de Dilatação**: se "Semestres utilizados pós dilatação" for negativo, considera o tamanho do estouro. Exemplo: -2 vira gap 2.

Alertas:
- Pós dilatação negativo: +{ALERTA_POS_DILATACAO_NEGATIVO} pontos
- Pós dilatação igual a 0 ou 1: +{ALERTA_POS_DILATACAO_ZERO_OU_UM} pontos
- Semestres restantes igual a 0 ou menor: +{ALERTA_SEMESTRES_RESTANTES_ZERO} pontos
- Semestres restantes igual a 1: +{ALERTA_SEMESTRES_RESTANTES_UM} pontos

Classificação:
- **Crítico**: score >= 75
- **Alto**: score >= 55
- **Médio**: score >= 35
- **Baixo**: score < 35

Isso ainda é uma regra inicial. A gente pode ajustar os pesos depois conforme tua regra de negócio.
"""
    )

# =========================
# ABAS
# =========================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Visão geral",
    "Ranking de risco",
    "Cursos",
    "Curso original x tratado",
    "Base detalhada",
])

with tab1:
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Distribuição por faixa de risco")
        risco_ordem = ["Crítico", "Alto", "Médio", "Baixo"]
        dist = filtro["Faixa de Risco"].value_counts().reindex(risco_ordem).fillna(0).reset_index()
        dist.columns = ["Faixa de Risco", "Quantidade"]
        fig = px.bar(dist, x="Faixa de Risco", y="Quantidade", text="Quantidade")
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Percentual de conclusão x saldo devedor")
        fig = px.scatter(
            filtro,
            x="Percentual Conclusão",
            y="Saldo devedor",
            color="Faixa de Risco",
            size="Score Criticidade",
            hover_data=["Nome", "Curso", "Curso original", "Semestres utilizados pós dilatação", "Motivo"],
        )
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Distribuição do percentual de conclusão")
    fig = px.histogram(filtro, x="Percentual Conclusão", nbins=12)
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Top alunos mais sensíveis")
    top_n = st.slider("Quantidade no ranking", 5, 50, 20)
    ranking = filtro.sort_values("Score Criticidade", ascending=False).head(top_n)

    fig = px.bar(
        ranking.sort_values("Score Criticidade"),
        x="Score Criticidade",
        y="Nome",
        orientation="h",
        hover_data=["Curso", "Curso original", "Percentual Conclusão", "Saldo devedor", "Motivo"],
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        ranking[[
            "Matrícula", "Nome", "Curso", "Curso original", "Percentual Conclusão", "Saldo devedor",
            "Semestres utilizados pós dilatação", "Semestres restantes", "Score Criticidade",
            "Faixa de Risco", "Motivo"
        ]],
        use_container_width=True,
        hide_index=True,
    )

with tab3:
    st.subheader("Resumo por curso tratado")
    resumo = filtro.groupby("Curso", as_index=False).agg(
        Alunos=("Nome", "count"),
        Saldo_Total=("Saldo devedor", "sum"),
        Media_Conclusao=("Percentual Conclusão", "mean"),
        Score_Medio=("Score Criticidade", "mean"),
        Criticos=("Faixa de Risco", lambda x: (x == "Crítico").sum()),
        Altos=("Faixa de Risco", lambda x: (x == "Alto").sum()),
    )
    resumo = resumo.sort_values(["Criticos", "Altos", "Score_Medio", "Saldo_Total"], ascending=False)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(resumo.head(15), x="Curso", y="Criticos", text="Criticos")
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(resumo.head(15), x="Curso", y="Saldo_Total", text_auto=".2s")
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(resumo, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Conferência: curso original x curso tratado")
    mapa = (
        df.groupby(["Curso", "Curso original"], as_index=False)
        .agg(Alunos=("Nome", "count"), Saldo_Total=("Saldo devedor", "sum"))
        .sort_values(["Curso", "Alunos"], ascending=[True, False])
    )
    st.dataframe(mapa, use_container_width=True, hide_index=True)

with tab5:
    st.subheader("Base detalhada")
    busca = st.text_input("Buscar por nome, matrícula, curso tratado ou curso original")
    detalhe = filtro.copy()

    if busca:
        termo = busca.lower()
        detalhe = detalhe[
            detalhe["Nome"].astype(str).str.lower().str.contains(termo, na=False)
            | detalhe["Matrícula"].astype(str).str.lower().str.contains(termo, na=False)
            | detalhe["Curso"].astype(str).str.lower().str.contains(termo, na=False)
            | detalhe["Curso original"].astype(str).str.lower().str.contains(termo, na=False)
        ]

    st.dataframe(
        detalhe.sort_values("Score Criticidade", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    csv = detalhe.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Baixar base filtrada em CSV",
        data=csv,
        file_name="analise_credito_educativo_filtrada.csv",
        mime="text/csv",
    )

st.divider()
st.caption("Score inicial: combinação de baixo percentual de conclusão, saldo devedor, semestres pós dilatação e semestres restantes. Os pesos podem ser ajustados conforme a regra de negócio.")

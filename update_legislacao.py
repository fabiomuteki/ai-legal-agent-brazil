#!/usr/bin/env python3
"""
update_legislacao.py
Verifica o status das leis de referência do agente jurídico brasileiro
e gera LEGISLACAO_ATUALIZADA.md.

Fontes (em ordem de tentativa):
  1. API Dados Abertos do Senado  — legis.senado.leg.br/dadosabertos
  2. LexML SRU                    — lexml.gov.br/busca/SRULocalData

Dependências: pip install requests
Uso:          python update_legislacao.py
Saída:        LEGISLACAO_ATUALIZADA.md
"""

import sys
import time
from datetime import date
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Instale as dependências: pip install requests defusedxml")

# defusedxml protege contra XXE em respostas XML de terceiros.
# Fallback para stdlib caso não esteja instalado (avisar o usuário).
try:
    from defusedxml import ElementTree as ET
    _DEFUSEDXML = True
except ImportError:
    from xml.etree import ElementTree as ET  # type: ignore[assignment]
    _DEFUSEDXML = False

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

SENADO_API       = "https://legis.senado.leg.br/dadosabertos/norma/lista"
LEXML_SRU        = "https://www.lexml.gov.br/busca/SRULocalData"
TIMEOUT          = 15
DELAY            = 1.2    # pausa entre requests
MAX_RESPONSE_MB  = 1      # tamanho máximo de resposta aceito (bytes)
MAX_RESPONSE_BYTES = MAX_RESPONSE_MB * 1024 * 1024

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; ai-legal-agent-brazil/1.0; "
        "+https://github.com/fabiomuteki/ai-legal-agent-brazil)"
    ),
    "Accept": "application/xml, text/xml, */*",
}

SRW_NS = "http://www.loc.gov/zing/srw/"

# ---------------------------------------------------------------------------
# Leis de referência
# ---------------------------------------------------------------------------

LEIS = [
    {
        "display": "CC — Lei 10.406/2002",
        "area": "Contratos em geral",
        "numero": "10406", "ano": "2002", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:2002-01-10;10406",
        "artigos": "arts. 47, 118, 121-137, 156-157, 166, 171, 264-285, 393, 413, 421-853",
        "planalto": "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm",
    },
    {
        "display": "CLT — Decreto-Lei 5.452/1943",
        "area": "Relações de trabalho",
        "numero": "5452", "ano": "1943", "tipo_senado": "DEL",
        "urn": "urn:lex:br:federal:decreto.lei:1943-05-01;5452",
        "artigos": "arts. 2º, 3º, 477 §6º, 484-A",
        "planalto": "https://www.planalto.gov.br/ccivil_03/decreto-lei/del5452compilado.htm",
    },
    {
        "display": "Reforma Trabalhista — Lei 13.467/2017",
        "area": "Relações de trabalho",
        "numero": "13467", "ano": "2017", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:2017-07-13;13467",
        "artigos": "",
        "planalto": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2017/lei/l13467.htm",
    },
    {
        "display": "CDC — Lei 8.078/1990",
        "area": "Proteção do consumidor",
        "numero": "8078", "ano": "1990", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:1990-09-11;8078",
        "artigos": "arts. 51, 54",
        "planalto": "https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm",
    },
    {
        "display": "LGPD — Lei 13.709/2018",
        "area": "Proteção de dados",
        "numero": "13709", "ano": "2018", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:2018-08-14;13709",
        "artigos": "arts. 7, 11, 15, 17-22, 33-36, 41, 46, 48",
        "planalto": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm",
    },
    {
        "display": "Lei de Direitos Autorais — 9.610/1998",
        "area": "Propriedade intelectual",
        "numero": "9610", "ano": "1998", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:1998-02-19;9610",
        "artigos": "art. 19",
        "planalto": "https://www.planalto.gov.br/ccivil_03/leis/l9610.htm",
    },
    {
        "display": "LPI — Lei 9.279/1996",
        "area": "Propriedade intelectual",
        "numero": "9279", "ano": "1996", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:1996-05-14;9279",
        "artigos": "arts. 2, 96, 122, 195",
        "planalto": "https://www.planalto.gov.br/ccivil_03/leis/l9279.htm",
    },
    {
        "display": "Lei de Software — 9.609/1998",
        "area": "Propriedade intelectual",
        "numero": "9609", "ano": "1998", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:1998-02-19;9609",
        "artigos": "art. 3",
        "planalto": "https://www.planalto.gov.br/ccivil_03/leis/l9609.htm",
    },
    {
        "display": "Lei do Inquilinato — 8.245/1991",
        "area": "Locação imobiliária",
        "numero": "8245", "ano": "1991", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:1991-10-18;8245",
        "artigos": "",
        "planalto": "https://www.planalto.gov.br/ccivil_03/leis/l8245.htm",
    },
    {
        "display": "Lei de Franquias — 13.966/2019",
        "area": "Franquias",
        "numero": "13966", "ano": "2019", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:2019-12-27;13966",
        "artigos": "prazo mínimo 14 dias (COF)",
        "planalto": "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/lei/l13966.htm",
    },
    {
        "display": "Nova Lei de Licitações — 14.133/2021",
        "area": "Licitações e contratos públicos",
        "numero": "14133", "ano": "2021", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:2021-04-01;14133",
        "artigos": "",
        "planalto": "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm",
    },
    {
        "display": "Lei das S/A — 6.404/1976",
        "area": "Sociedades empresariais",
        "numero": "6404", "ano": "1976", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:1976-12-15;6404",
        "artigos": "arts. 168-170",
        "planalto": "https://www.planalto.gov.br/ccivil_03/leis/l6404compilada.htm",
    },
    {
        "display": "Marco Legal das Startups — LC 182/2021",
        "area": "Startups e inovação",
        "numero": "182", "ano": "2021", "tipo_senado": "LCP",
        "urn": "urn:lex:br:federal:lei.complementar:2021-06-17;182",
        "artigos": "arts. 2, 43-47",
        "planalto": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp182.htm",
    },
    {
        "display": "Lei do Ambiente de Negócios — 14.195/2021",
        "area": "Startups e inovação",
        "numero": "14195", "ano": "2021", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:2021-08-26;14195",
        "artigos": "",
        "planalto": "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14195.htm",
    },
    {
        "display": "Lei de Arbitragem — 9.307/1996",
        "area": "Arbitragem e mediação",
        "numero": "9307", "ano": "1996", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:1996-09-23;9307",
        "artigos": "",
        "planalto": "https://www.planalto.gov.br/ccivil_03/leis/l9307.htm",
    },
    {
        "display": "Lei de Mediação — 13.140/2015",
        "area": "Arbitragem e mediação",
        "numero": "13140", "ano": "2015", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:2015-06-26;13140",
        "artigos": "",
        "planalto": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13140.htm",
    },
    {
        "display": "Marco Civil da Internet — 12.965/2014",
        "area": "Contratos digitais",
        "numero": "12965", "ano": "2014", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:2014-04-23;12965",
        "artigos": "",
        "planalto": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2014/lei/l12965.htm",
    },
    {
        "display": "Lei de Assinaturas Eletrônicas — 14.063/2020",
        "area": "Contratos digitais",
        "numero": "14063", "ano": "2020", "tipo_senado": "LEI",
        "urn": "urn:lex:br:federal:lei:2020-09-21;14063",
        "artigos": "",
        "planalto": "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2020/lei/l14063.htm",
    },
    {
        "display": "ICP-Brasil — MP 2.200-2/2001",
        "area": "Contratos digitais",
        "numero": "2200", "ano": "2001", "tipo_senado": "MPV",
        "urn": "urn:lex:br:federal:medida.provisoria:2001-08-24;2200-2",
        "artigos": "",
        "planalto": "https://www.planalto.gov.br/ccivil_03/mpv/antigas_2001/2200-2.htm",
    },
]

# ---------------------------------------------------------------------------
# Camada de rede
# ---------------------------------------------------------------------------

def _get(url: str, params: dict | None = None) -> requests.Response | None:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        # Rejeita respostas muito grandes antes de fazer parse
        content_length = int(r.headers.get("Content-Length", 0))
        if content_length > MAX_RESPONSE_BYTES:
            print(f"resposta muito grande ({content_length} bytes)", file=sys.stderr, end=" ")
            return None
        if len(r.content) > MAX_RESPONSE_BYTES:
            print("resposta muito grande", file=sys.stderr, end=" ")
            return None
        return r
    except requests.exceptions.Timeout:
        print("timeout", file=sys.stderr, end=" ")
        return None
    except requests.exceptions.HTTPError as exc:
        print(f"HTTP {exc.response.status_code}", file=sys.stderr, end=" ")
        return None
    except requests.exceptions.ConnectionError:
        print("conexão recusada", file=sys.stderr, end=" ")
        return None

# ---------------------------------------------------------------------------
# Fonte 1: API Dados Abertos do Senado
# ---------------------------------------------------------------------------

def _verificar_senado(lei: dict) -> bool | None:
    """
    Retorna True se encontrado, False se não encontrado, None se erro/indisponível.
    Endpoint: GET /norma/lista?numero=NNNN&ano=YYYY&sigla=LEI
    """
    r = _get(SENADO_API, {
        "numero": lei["numero"],
        "ano":    lei["ano"],
        "sigla":  lei["tipo_senado"],
    })
    if r is None:
        return None
    try:
        root = ET.fromstring(r.text)
        # Resposta: <ListaNormas> com zero ou mais <Norma> filhos
        normas = root.findall(".//Norma")
        return len(normas) > 0
    except ET.ParseError:
        return None

# ---------------------------------------------------------------------------
# Fonte 2: LexML SRU (fallback)
# ---------------------------------------------------------------------------

def _verificar_lexml(urn: str) -> bool | None:
    """
    Retorna True se encontrado, False se não, None se erro.
    Tenta URN exato; se falhar, tenta por número.
    """
    def _query(q: str) -> bool | None:
        r = _get(LEXML_SRU, {
            "operation":      "searchRetrieve",
            "version":        "1.1",
            "query":          q,
            "maximumRecords": "1",
        })
        if r is None:
            return None
        try:
            root = ET.fromstring(r.text)
            el = root.find(f"{{{SRW_NS}}}numberOfRecords")
            return el is not None and el.text.strip() != "0"
        except ET.ParseError:
            return None

    resultado = _query(f'urn = "{urn}"')
    if resultado is True:
        return True

    numero = urn.split(";")[-1]
    return _query(f'urn any "{numero}"')

# ---------------------------------------------------------------------------
# Verificação unificada
# ---------------------------------------------------------------------------

def verificar(lei: dict) -> tuple[str, str]:
    """
    Retorna (status_label, emoji).
    Tenta Senado primeiro; cai no LexML se Senado falhar.
    """
    # Tentativa 1: Senado
    resultado = _verificar_senado(lei)
    if resultado is True:
        return "indexado (Senado)", "✅"
    if resultado is False:
        # Senado respondeu, mas não achou — tenta LexML antes de dar ❌
        pass

    # Tentativa 2: LexML
    time.sleep(DELAY / 2)
    resultado_lexml = _verificar_lexml(lei["urn"])
    if resultado_lexml is True:
        return "indexado (LexML)", "✅"
    if resultado_lexml is False:
        return "não encontrado", "❌"

    # Ambos falharam (sem conectividade)
    return "sem conectividade", "🔴"

# ---------------------------------------------------------------------------
# Geração do Markdown
# ---------------------------------------------------------------------------

def gerar_markdown(resultados: list[dict]) -> str:
    hoje = date.today().isoformat()
    linhas = [
        "# Legislação de Referência — Status Verificado",
        "",
        f"> **Gerado em:** {hoje}",
        "> **Fontes:** API Dados Abertos do Senado (primária) · LexML SRU (secundária)",
        ">",
        "> ✅ Encontrado e indexado  |  ❌ Não encontrado  |  🔴 Sem conectividade com as fontes",
        "",
        "---",
        "",
        "| Área | Lei | Artigos de referência | Status | Texto oficial |",
        "|---|---|---|---|---|",
    ]

    for r in resultados:
        linha = (
            f"| {r['area']} "
            f"| {r['display']} "
            f"| {r['artigos'] or '—'} "
            f"| {r['emoji']} {r['status']} "
            f"| [Planalto]({r['planalto']}) |"
        )
        linhas.append(linha)

    todas_ok   = all(r["emoji"] == "✅" for r in resultados)
    sem_conn   = all(r["emoji"] == "🔴" for r in resultados)

    linhas += [
        "",
        "---",
        "",
        "## Interpretação dos resultados",
        "",
    ]

    if sem_conn:
        linhas += [
            "⚠️ **Nenhuma fonte respondeu.** O script precisa de acesso à internet para funcionar.",
            "Execute-o em uma máquina com acesso a `legis.senado.leg.br` e `lexml.gov.br`.",
        ]
    elif todas_ok:
        linhas += [
            "✅ Todas as leis foram localizadas nas fontes oficiais.",
            "Acesse os links do Planalto para conferir o texto consolidado atualizado.",
        ]
    else:
        n_err = sum(1 for r in resultados if r["emoji"] != "✅")
        linhas += [
            f"⚠️ {n_err} lei(s) marcada(s) como ❌ ou 🔴 — verifique manualmente os links do Planalto.",
        ]

    linhas += [
        "",
        "## Como usar",
        "",
        "1. **Rode periodicamente** (sugestão: mensal, ou após notícia de alteração legislativa)",
        "2. **Leis ❌ ou 🔴**: acesse o link do Planalto para confirmar se continuam vigentes",
        "3. **Adicione este arquivo** ao contexto do projeto no Claude.ai para que o agente",
        "   use-o como referência complementar ao AGENT.md",
        "",
        "> ℹ️ Este arquivo verifica **indexação** das leis nas fontes oficiais.",
        "> Para o texto atualizado de artigos específicos, acesse os links do Planalto.",
    ]

    return "\n".join(linhas)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not _DEFUSEDXML:
        print(
            "⚠️  defusedxml não instalado — usando xml.etree (sem proteção XXE).\n"
            "   Instale com: pip install defusedxml\n"
        )
    print(f"Verificando {len(LEIS)} leis (Senado → LexML)...\n")
    resultados = []

    for i, lei in enumerate(LEIS, 1):
        print(f"[{i:02}/{len(LEIS)}] {lei['display']}", end=" ... ", flush=True)
        status, emoji = verificar(lei)
        print(emoji, status)
        resultados.append({**lei, "status": status, "emoji": emoji})
        if i < len(LEIS):
            time.sleep(DELAY)

    output = Path("LEGISLACAO_ATUALIZADA.md")
    output.write_text(gerar_markdown(resultados), encoding="utf-8")

    ok   = sum(1 for r in resultados if r["emoji"] == "✅")
    err  = sum(1 for r in resultados if r["emoji"] != "✅")

    print(f"\n{'─' * 50}")
    print(f"✅ {ok} encontradas  |  ❌/🔴 {err} com problema")
    print(f"Saída: {output.resolve()}")

    if all(r["emoji"] == "🔴" for r in resultados):
        print("\n⚠️  Sem conectividade com as fontes. Execute localmente com acesso à internet.")
        sys.exit(1)


if __name__ == "__main__":
    main()

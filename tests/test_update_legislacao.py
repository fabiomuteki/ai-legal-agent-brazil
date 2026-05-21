"""
test_update_legislacao.py
Test suite for update_legislacao.py using unittest + unittest.mock.
No real network requests are made.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Make sure the project root is on the path so we can import the module
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests as _requests_module
import update_legislacao as mod
from update_legislacao import (
    _get,
    _verificar_senado,
    _verificar_lexml,
    verificar,
    gerar_markdown,
    LEIS,
    SENADO_API,
    LEXML_SRU,
    SRW_NS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(text: str, status_code: int = 200) -> MagicMock:
    """Build a minimal mock requests.Response."""
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.raise_for_status = MagicMock()  # no-op by default (200)
    return r


def _make_http_error(status_code: int) -> _requests_module.exceptions.HTTPError:
    """Create an HTTPError with a fake response carrying status_code."""
    resp = MagicMock()
    resp.status_code = status_code
    exc = _requests_module.exceptions.HTTPError(response=resp)
    return exc


SENADO_FOUND_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ListaNormas>
  <Norma><Sigla>LEI</Sigla><Numero>10406</Numero><Ano>2002</Ano></Norma>
</ListaNormas>"""

SENADO_EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ListaNormas/>"""

LEXML_FOUND_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<searchRetrieveResponse xmlns="{SRW_NS}">
  <numberOfRecords>5</numberOfRecords>
</searchRetrieveResponse>"""

LEXML_ZERO_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<searchRetrieveResponse xmlns="{SRW_NS}">
  <numberOfRecords>0</numberOfRecords>
</searchRetrieveResponse>"""

SAMPLE_LEI = {
    "display": "CC — Lei 10.406/2002",
    "area": "Contratos em geral",
    "numero": "10406",
    "ano": "2002",
    "tipo_senado": "LEI",
    "urn": "urn:lex:br:federal:lei:2002-01-10;10406",
    "artigos": "arts. 47, 118",
    "planalto": "https://www.planalto.gov.br/ccivil_03/leis/2002/l10406compilada.htm",
}


# ===========================================================================
# Tests for _get
# ===========================================================================

class TestGet(unittest.TestCase):

    @patch("update_legislacao.requests.get")
    def test_returns_response_on_success(self, mock_get):
        """_get returns the Response object when the request succeeds (200)."""
        mock_resp = _make_response("OK", 200)
        mock_get.return_value = mock_resp

        result = _get("https://example.com", {"q": "test"})

        self.assertIs(result, mock_resp)
        mock_get.assert_called_once()

    @patch("update_legislacao.requests.get")
    def test_returns_none_on_timeout(self, mock_get):
        """_get returns None when a Timeout exception is raised."""
        mock_get.side_effect = _requests_module.exceptions.Timeout()

        result = _get("https://example.com")

        self.assertIsNone(result)

    @patch("update_legislacao.requests.get")
    def test_returns_none_on_http_error(self, mock_get):
        """_get returns None when an HTTPError is raised (e.g., 404, 500)."""
        mock_resp = _make_response("Not Found", 404)
        mock_resp.raise_for_status.side_effect = _make_http_error(404)
        mock_get.return_value = mock_resp

        result = _get("https://example.com")

        self.assertIsNone(result)

    @patch("update_legislacao.requests.get")
    def test_returns_none_on_connection_error(self, mock_get):
        """_get returns None when a ConnectionError is raised."""
        mock_get.side_effect = _requests_module.exceptions.ConnectionError()

        result = _get("https://example.com")

        self.assertIsNone(result)

    @patch("update_legislacao.requests.get")
    def test_passes_params_and_headers(self, mock_get):
        """_get passes the correct params and headers to requests.get."""
        mock_get.return_value = _make_response("OK")
        params = {"numero": "10406", "ano": "2002"}

        _get("https://example.com", params)

        call_kwargs = mock_get.call_args
        self.assertEqual(call_kwargs[1]["params"], params)
        self.assertIn("User-Agent", call_kwargs[1]["headers"])

    @patch("update_legislacao.requests.get")
    def test_returns_none_on_500_http_error(self, mock_get):
        """_get returns None for 500 Internal Server Error."""
        mock_resp = _make_response("Server Error", 500)
        mock_resp.raise_for_status.side_effect = _make_http_error(500)
        mock_get.return_value = mock_resp

        result = _get("https://example.com")

        self.assertIsNone(result)

    @patch("update_legislacao.requests.get")
    def test_no_params_defaults_to_none(self, mock_get):
        """_get can be called without params."""
        mock_get.return_value = _make_response("OK")

        result = _get("https://example.com")

        self.assertIsNotNone(result)
        call_kwargs = mock_get.call_args
        self.assertIsNone(call_kwargs[1]["params"])


# ===========================================================================
# Tests for _verificar_senado
# ===========================================================================

class TestVerificarSenado(unittest.TestCase):

    @patch("update_legislacao._get")
    def test_returns_true_when_norma_found(self, mock_get):
        """Returns True when XML response contains <Norma> elements."""
        mock_get.return_value = _make_response(SENADO_FOUND_XML)

        result = _verificar_senado(SAMPLE_LEI)

        self.assertTrue(result)

    @patch("update_legislacao._get")
    def test_returns_false_when_no_norma(self, mock_get):
        """Returns False when XML response has no <Norma> elements."""
        mock_get.return_value = _make_response(SENADO_EMPTY_XML)

        result = _verificar_senado(SAMPLE_LEI)

        self.assertFalse(result)

    @patch("update_legislacao._get")
    def test_returns_none_when_get_returns_none(self, mock_get):
        """Returns None when _get returns None (network error)."""
        mock_get.return_value = None

        result = _verificar_senado(SAMPLE_LEI)

        self.assertIsNone(result)

    @patch("update_legislacao._get")
    def test_returns_none_on_malformed_xml(self, mock_get):
        """Returns None when the response body is not valid XML."""
        mock_get.return_value = _make_response("this is not xml at all <<<")

        result = _verificar_senado(SAMPLE_LEI)

        self.assertIsNone(result)

    @patch("update_legislacao._get")
    def test_calls_senado_api_with_correct_params(self, mock_get):
        """Passes correct numero/ano/sigla params to _get."""
        mock_get.return_value = _make_response(SENADO_FOUND_XML)

        _verificar_senado(SAMPLE_LEI)

        mock_get.assert_called_once_with(
            SENADO_API,
            {
                "numero": SAMPLE_LEI["numero"],
                "ano":    SAMPLE_LEI["ano"],
                "sigla":  SAMPLE_LEI["tipo_senado"],
            },
        )

    @patch("update_legislacao._get")
    def test_returns_true_with_multiple_normas(self, mock_get):
        """Returns True when multiple <Norma> elements are present."""
        xml = """<ListaNormas>
          <Norma><Numero>1</Numero></Norma>
          <Norma><Numero>2</Numero></Norma>
        </ListaNormas>"""
        mock_get.return_value = _make_response(xml)

        result = _verificar_senado(SAMPLE_LEI)

        self.assertTrue(result)

    @patch("update_legislacao._get")
    def test_returns_none_on_empty_response_body(self, mock_get):
        """Returns None when response body is empty (cannot parse XML)."""
        mock_get.return_value = _make_response("")

        result = _verificar_senado(SAMPLE_LEI)

        self.assertIsNone(result)


# ===========================================================================
# Tests for _verificar_lexml
# ===========================================================================

class TestVerificarLexml(unittest.TestCase):

    @patch("update_legislacao._get")
    def test_returns_true_on_exact_urn_match(self, mock_get):
        """Returns True immediately when the URN query returns numberOfRecords > 0."""
        mock_get.return_value = _make_response(LEXML_FOUND_XML)

        result = _verificar_lexml(SAMPLE_LEI["urn"])

        self.assertTrue(result)
        # Should only call _get once (exact match, no fallback needed)
        self.assertEqual(mock_get.call_count, 1)

    @patch("update_legislacao._get")
    def test_returns_true_via_fallback_number_search(self, mock_get):
        """Returns True via number fallback when exact URN returns 0 but number query returns > 0."""
        zero_resp = _make_response(LEXML_ZERO_XML)
        found_resp = _make_response(LEXML_FOUND_XML)
        mock_get.side_effect = [zero_resp, found_resp]

        result = _verificar_lexml(SAMPLE_LEI["urn"])

        self.assertTrue(result)
        self.assertEqual(mock_get.call_count, 2)

    @patch("update_legislacao._get")
    def test_returns_false_when_both_queries_return_zero(self, mock_get):
        """Returns False when both URN and fallback queries return 0 records."""
        mock_get.return_value = _make_response(LEXML_ZERO_XML)

        result = _verificar_lexml(SAMPLE_LEI["urn"])

        self.assertFalse(result)
        self.assertEqual(mock_get.call_count, 2)

    @patch("update_legislacao._get")
    def test_returns_none_when_first_get_returns_none(self, mock_get):
        """Returns None (from fallback) when _get returns None on first call."""
        # First call returns None → resultado is None (not True), so fallback runs.
        # Second call also returns None → fallback returns None.
        mock_get.return_value = None

        result = _verificar_lexml(SAMPLE_LEI["urn"])

        self.assertIsNone(result)

    @patch("update_legislacao._get")
    def test_returns_none_on_malformed_xml(self, mock_get):
        """Returns None when the XML cannot be parsed."""
        mock_get.return_value = _make_response("<<< invalid xml")

        result = _verificar_lexml(SAMPLE_LEI["urn"])

        # Both queries fail to parse → fallback also returns None
        self.assertIsNone(result)

    @patch("update_legislacao._get")
    def test_fallback_uses_number_part_of_urn(self, mock_get):
        """Fallback query uses the part after ';' in the URN as the number."""
        zero_resp = _make_response(LEXML_ZERO_XML)
        found_resp = _make_response(LEXML_FOUND_XML)
        mock_get.side_effect = [zero_resp, found_resp]

        _verificar_lexml("urn:lex:br:federal:lei:2002-01-10;10406")

        # Second call should use '10406' as search term
        second_call_params = mock_get.call_args_list[1][0][1]
        self.assertIn("10406", second_call_params["query"])

    @patch("update_legislacao._get")
    def test_exact_urn_query_is_first_call(self, mock_get):
        """First query uses the full URN string."""
        mock_get.return_value = _make_response(LEXML_FOUND_XML)
        urn = SAMPLE_LEI["urn"]

        _verificar_lexml(urn)

        first_call_params = mock_get.call_args_list[0][0][1]
        self.assertIn(urn, first_call_params["query"])

    @patch("update_legislacao._get")
    def test_number_of_records_zero_string_is_false(self, mock_get):
        """numberOfRecords element with text '0' is treated as not found."""
        xml = f"""<searchRetrieveResponse xmlns="{SRW_NS}">
          <numberOfRecords>0</numberOfRecords>
        </searchRetrieveResponse>"""
        mock_get.return_value = _make_response(xml)

        result = _verificar_lexml(SAMPLE_LEI["urn"])

        self.assertFalse(result)

    @patch("update_legislacao._get")
    def test_number_of_records_nonzero_is_true(self, mock_get):
        """numberOfRecords element with non-zero text is treated as found."""
        xml = f"""<searchRetrieveResponse xmlns="{SRW_NS}">
          <numberOfRecords>1</numberOfRecords>
        </searchRetrieveResponse>"""
        mock_get.return_value = _make_response(xml)

        result = _verificar_lexml(SAMPLE_LEI["urn"])

        self.assertTrue(result)


# ===========================================================================
# Tests for verificar
# ===========================================================================

class TestVerificar(unittest.TestCase):

    @patch("update_legislacao.time.sleep")
    @patch("update_legislacao._verificar_lexml")
    @patch("update_legislacao._verificar_senado")
    def test_senado_true_returns_indexado_senado(self, mock_senado, mock_lexml, mock_sleep):
        """When Senado returns True, returns ('indexado (Senado)', '✅') immediately."""
        mock_senado.return_value = True

        status, emoji = verificar(SAMPLE_LEI)

        self.assertEqual(status, "indexado (Senado)")
        self.assertEqual(emoji, "✅")

    @patch("update_legislacao.time.sleep")
    @patch("update_legislacao._verificar_lexml")
    @patch("update_legislacao._verificar_senado")
    def test_senado_true_does_not_call_lexml(self, mock_senado, mock_lexml, mock_sleep):
        """When Senado returns True, LexML is NOT consulted."""
        mock_senado.return_value = True

        verificar(SAMPLE_LEI)

        mock_lexml.assert_not_called()

    @patch("update_legislacao.time.sleep")
    @patch("update_legislacao._verificar_lexml")
    @patch("update_legislacao._verificar_senado")
    def test_senado_none_falls_back_to_lexml_true(self, mock_senado, mock_lexml, mock_sleep):
        """When Senado returns None (error), falls back to LexML; returns LexML result if True."""
        mock_senado.return_value = None
        mock_lexml.return_value = True

        status, emoji = verificar(SAMPLE_LEI)

        self.assertEqual(status, "indexado (LexML)")
        self.assertEqual(emoji, "✅")
        mock_lexml.assert_called_once_with(SAMPLE_LEI["urn"])

    @patch("update_legislacao.time.sleep")
    @patch("update_legislacao._verificar_lexml")
    @patch("update_legislacao._verificar_senado")
    def test_senado_false_falls_back_to_lexml_true(self, mock_senado, mock_lexml, mock_sleep):
        """When Senado returns False, also falls back to LexML; returns LexML if True."""
        mock_senado.return_value = False
        mock_lexml.return_value = True

        status, emoji = verificar(SAMPLE_LEI)

        self.assertEqual(status, "indexado (LexML)")
        self.assertEqual(emoji, "✅")

    @patch("update_legislacao.time.sleep")
    @patch("update_legislacao._verificar_lexml")
    @patch("update_legislacao._verificar_senado")
    def test_senado_false_lexml_false_returns_nao_encontrado(self, mock_senado, mock_lexml, mock_sleep):
        """When Senado=False and LexML=False, returns ('não encontrado', '❌')."""
        mock_senado.return_value = False
        mock_lexml.return_value = False

        status, emoji = verificar(SAMPLE_LEI)

        self.assertEqual(status, "não encontrado")
        self.assertEqual(emoji, "❌")

    @patch("update_legislacao.time.sleep")
    @patch("update_legislacao._verificar_lexml")
    @patch("update_legislacao._verificar_senado")
    def test_both_none_returns_sem_conectividade(self, mock_senado, mock_lexml, mock_sleep):
        """When both Senado and LexML return None, returns ('sem conectividade', '🔴')."""
        mock_senado.return_value = None
        mock_lexml.return_value = None

        status, emoji = verificar(SAMPLE_LEI)

        self.assertEqual(status, "sem conectividade")
        self.assertEqual(emoji, "🔴")

    @patch("update_legislacao.time.sleep")
    @patch("update_legislacao._verificar_lexml")
    @patch("update_legislacao._verificar_senado")
    def test_senado_false_lexml_none_returns_sem_conectividade(self, mock_senado, mock_lexml, mock_sleep):
        """When Senado=False but LexML=None, returns sem conectividade."""
        mock_senado.return_value = False
        mock_lexml.return_value = None

        status, emoji = verificar(SAMPLE_LEI)

        self.assertEqual(status, "sem conectividade")
        self.assertEqual(emoji, "🔴")

    @patch("update_legislacao.time.sleep")
    @patch("update_legislacao._verificar_lexml")
    @patch("update_legislacao._verificar_senado")
    def test_verificar_sleeps_between_sources(self, mock_senado, mock_lexml, mock_sleep):
        """verificar calls time.sleep before invoking LexML."""
        mock_senado.return_value = None
        mock_lexml.return_value = True

        verificar(SAMPLE_LEI)

        mock_sleep.assert_called_once()

    @patch("update_legislacao.time.sleep")
    @patch("update_legislacao._verificar_lexml")
    @patch("update_legislacao._verificar_senado")
    def test_verificar_passes_urn_to_lexml(self, mock_senado, mock_lexml, mock_sleep):
        """verificar passes lei['urn'] to _verificar_lexml."""
        mock_senado.return_value = None
        mock_lexml.return_value = False

        verificar(SAMPLE_LEI)

        mock_lexml.assert_called_once_with(SAMPLE_LEI["urn"])

    @patch("update_legislacao.time.sleep")
    @patch("update_legislacao._verificar_lexml")
    @patch("update_legislacao._verificar_senado")
    def test_return_type_is_tuple_of_two_strings(self, mock_senado, mock_lexml, mock_sleep):
        """verificar always returns a 2-tuple of strings."""
        for senado_val, lexml_val in [
            (True, None), (False, True), (False, False), (None, None),
        ]:
            with self.subTest(senado=senado_val, lexml=lexml_val):
                mock_senado.return_value = senado_val
                mock_lexml.return_value = lexml_val

                result = verificar(SAMPLE_LEI)

                self.assertIsInstance(result, tuple)
                self.assertEqual(len(result), 2)
                self.assertIsInstance(result[0], str)
                self.assertIsInstance(result[1], str)


# ===========================================================================
# Tests for gerar_markdown
# ===========================================================================

def _make_resultado(emoji: str, status: str) -> dict:
    return {
        "display": "CC — Lei 10.406/2002",
        "area": "Contratos em geral",
        "artigos": "arts. 47",
        "planalto": "https://www.planalto.gov.br/leis/l10406.htm",
        "status": status,
        "emoji": emoji,
    }


class TestGerarMarkdown(unittest.TestCase):

    def setUp(self):
        self.resultado_ok = _make_resultado("✅", "indexado (Senado)")
        self.resultado_err = _make_resultado("❌", "não encontrado")
        self.resultado_conn = _make_resultado("🔴", "sem conectividade")

    def test_contains_main_header(self):
        """Output includes the main H1 header."""
        md = gerar_markdown([self.resultado_ok])
        self.assertIn("# Legislação de Referência — Status Verificado", md)

    def test_contains_table_header_row(self):
        """Output includes the Markdown table header."""
        md = gerar_markdown([self.resultado_ok])
        self.assertIn("| Área | Lei | Artigos de referência | Status | Texto oficial |", md)

    def test_contains_table_separator_row(self):
        """Output includes the Markdown table separator."""
        md = gerar_markdown([self.resultado_ok])
        self.assertIn("|---|---|---|---|---|", md)

    def test_table_row_for_each_result(self):
        """Each result dict generates exactly one table row."""
        resultados = [
            _make_resultado("✅", "indexado (Senado)"),
            _make_resultado("❌", "não encontrado"),
        ]
        md = gerar_markdown(resultados)
        # Count rows with pipe separators that are data rows (not header/separator)
        data_rows = [
            line for line in md.splitlines()
            if line.startswith("| ") and "Área" not in line and "---" not in line
        ]
        self.assertEqual(len(data_rows), 2)

    def test_row_contains_area_display_artigos_status_planalto(self):
        """Each table row includes area, display, artigos, status+emoji, and planalto link."""
        md = gerar_markdown([self.resultado_ok])
        self.assertIn("Contratos em geral", md)
        self.assertIn("CC — Lei 10.406/2002", md)
        self.assertIn("arts. 47", md)
        self.assertIn("✅", md)
        self.assertIn("indexado (Senado)", md)
        self.assertIn("[Planalto](", md)

    def test_empty_artigos_shows_dash(self):
        """When artigos is empty, the table cell shows '—'."""
        resultado = _make_resultado("✅", "indexado (Senado)")
        resultado["artigos"] = ""
        md = gerar_markdown([resultado])
        self.assertIn("| — |", md)

    def test_all_red_shows_connectivity_warning(self):
        """When all results are 🔴, shows connectivity warning."""
        resultados = [self.resultado_conn, self.resultado_conn]
        md = gerar_markdown(resultados)
        self.assertIn("Nenhuma fonte respondeu", md)

    def test_all_green_shows_ok_message(self):
        """When all results are ✅, shows the 'all found' ok message."""
        resultados = [self.resultado_ok, self.resultado_ok]
        md = gerar_markdown(resultados)
        self.assertIn("Todas as leis foram localizadas nas fontes oficiais", md)

    def test_mixed_results_shows_error_count(self):
        """When results are mixed, shows count of laws with issues."""
        resultados = [
            self.resultado_ok,
            self.resultado_err,
            self.resultado_conn,
        ]
        md = gerar_markdown(resultados)
        # 2 laws are not ✅
        self.assertIn("2 lei(s)", md)

    def test_contains_date(self):
        """Output includes today's date."""
        from datetime import date
        md = gerar_markdown([self.resultado_ok])
        self.assertIn(date.today().isoformat(), md)

    def test_contains_sources_line(self):
        """Output mentions both data sources."""
        md = gerar_markdown([self.resultado_ok])
        self.assertIn("Senado", md)
        self.assertIn("LexML", md)

    def test_contains_como_usar_section(self):
        """Output includes the 'Como usar' section."""
        md = gerar_markdown([self.resultado_ok])
        self.assertIn("## Como usar", md)

    def test_contains_interpretacao_section(self):
        """Output includes the 'Interpretação dos resultados' section."""
        md = gerar_markdown([self.resultado_ok])
        self.assertIn("## Interpretação dos resultados", md)

    def test_returns_string(self):
        """gerar_markdown returns a string."""
        result = gerar_markdown([self.resultado_ok])
        self.assertIsInstance(result, str)

    def test_connectivity_warning_not_shown_when_mixed(self):
        """The connectivity-only warning is not shown when results are mixed."""
        resultados = [self.resultado_ok, self.resultado_conn]
        md = gerar_markdown(resultados)
        self.assertNotIn("Nenhuma fonte respondeu", md)

    def test_all_ok_message_not_shown_when_mixed(self):
        """The all-ok message is not shown when some results are not ✅."""
        resultados = [self.resultado_ok, self.resultado_err]
        md = gerar_markdown(resultados)
        self.assertNotIn("Todas as leis foram localizadas", md)

    def test_single_error_message(self):
        """When there is one error, shows '1 lei(s)' in the message."""
        resultados = [self.resultado_ok, self.resultado_err]
        md = gerar_markdown(resultados)
        self.assertIn("1 lei(s)", md)


# ===========================================================================
# Tests for LEIS data integrity
# ===========================================================================

REQUIRED_KEYS = {"display", "area", "numero", "ano", "tipo_senado", "urn", "artigos", "planalto"}


class TestLeisDataIntegrity(unittest.TestCase):

    def test_leis_is_nonempty_list(self):
        """LEIS is a non-empty list."""
        self.assertIsInstance(LEIS, list)
        self.assertGreater(len(LEIS), 0)

    def test_all_entries_have_required_keys(self):
        """Every entry in LEIS has all required keys."""
        for lei in LEIS:
            with self.subTest(display=lei.get("display", "<unknown>")):
                missing = REQUIRED_KEYS - set(lei.keys())
                self.assertFalse(
                    missing,
                    f"Entry '{lei.get('display')}' is missing keys: {missing}",
                )

    def test_all_urns_start_with_urn_lex_br_federal(self):
        """Every URN starts with 'urn:lex:br:federal:'."""
        for lei in LEIS:
            with self.subTest(display=lei.get("display")):
                self.assertTrue(
                    lei["urn"].startswith("urn:lex:br:federal:"),
                    f"URN does not start with 'urn:lex:br:federal:': {lei['urn']}",
                )

    def test_all_string_values_are_strings(self):
        """All required key values in LEIS entries are strings."""
        for lei in LEIS:
            for key in REQUIRED_KEYS:
                with self.subTest(display=lei.get("display"), key=key):
                    self.assertIsInstance(
                        lei[key], str,
                        f"Key '{key}' in '{lei.get('display')}' is not a string",
                    )

    def test_planalto_links_start_with_https(self):
        """All planalto URLs start with 'https://'."""
        for lei in LEIS:
            with self.subTest(display=lei.get("display")):
                self.assertTrue(
                    lei["planalto"].startswith("https://"),
                    f"planalto URL does not start with 'https://': {lei['planalto']}",
                )

    def test_no_duplicate_urns(self):
        """All URNs in LEIS are unique."""
        urns = [lei["urn"] for lei in LEIS]
        self.assertEqual(len(urns), len(set(urns)), "Duplicate URNs found in LEIS")

    def test_all_anos_are_numeric_strings(self):
        """All 'ano' values are strings containing only digits."""
        for lei in LEIS:
            with self.subTest(display=lei.get("display")):
                self.assertTrue(
                    lei["ano"].isdigit(),
                    f"'ano' is not a numeric string: {lei['ano']}",
                )

    def test_all_numeros_are_numeric_strings(self):
        """All 'numero' values are strings containing only digits."""
        for lei in LEIS:
            with self.subTest(display=lei.get("display")):
                self.assertTrue(
                    lei["numero"].isdigit(),
                    f"'numero' is not a numeric string for '{lei.get('display')}': {lei['numero']}",
                )


if __name__ == "__main__":
    unittest.main()

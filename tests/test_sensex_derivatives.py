"""Unit tests for BSE SENSEX Option Chain, F&O eligibility, and derivatives intelligence."""

import pandas as pd
from unittest.mock import patch, MagicMock

from earnings_engine.data.universe import is_fno_eligible, resolve_fno_symbol, load_nse_fno
from earnings_engine.data.options_chart_engine import INDEX_MAP
from earnings_engine.data.providers.provider_manager import DataProviderManager, get_data_manager


def test_sensex_fno_eligibility():
    """Verify SENSEX and its aliases are recognized as eligible F&O symbols."""
    assert is_fno_eligible("SENSEX") is True
    assert is_fno_eligible("SENSEX.BO") is True
    assert is_fno_eligible("^BSESN") is True
    assert is_fno_eligible("BSESENSEX") is True
    assert is_fno_eligible("BSE:SENSEX") is True

    assert resolve_fno_symbol("SENSEX") == "SENSEX"
    assert resolve_fno_symbol("^BSESN") == "SENSEX"
    assert resolve_fno_symbol("BSESENSEX") == "SENSEX"

    fno_list = load_nse_fno()
    assert "SENSEX" in fno_list or any("SENSEX" in s for s in fno_list)


def test_sensex_index_map():
    """Verify SENSEX aliases map properly to ^BSESN for chart intelligence."""
    assert INDEX_MAP.get("SENSEX") == "^BSESN"
    assert INDEX_MAP.get("BSESENSEX") == "^BSESN"
    assert INDEX_MAP.get("BSE:SENSEX") == "^BSESN"


def test_provider_manager_bse_option_chain_routing():
    """Verify DataProviderManager routes SENSEX to fetch_bse_option_chain."""
    mgr = DataProviderManager()

    with patch.object(mgr, "fetch_bse_option_chain", return_value={"symbol": "SENSEX", "data": []}) as mock_bse:
        res = mgr.fetch_option_chain("SENSEX")
        assert mock_bse.called
        assert res["symbol"] == "SENSEX"

    with patch.object(mgr, "fetch_bse_option_chain", return_value={"symbol": "SENSEX", "data": []}) as mock_bse:
        res = mgr.fetch_option_chain("^BSESN")
        assert mock_bse.called
        assert res["symbol"] == "SENSEX"


def test_bse_bhavcopy_parsing():
    """Verify BSE FO Bhavcopy parsing logic handles IDO index options."""
    mgr = DataProviderManager()

    sample_bse_csv = (
        "TckrSymb,FinInstrmTp,StrkPric,XpryDt,OptnTp,ClsPric,PrvsClsgPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,LastPric,TtlTrfVal,UndrlygPric\n"
        "SENSEX,IDO,75000.0,2025-04-24,CE,500.0,450.0,1200,200,500,510.0,250000.0,75200.0\n"
        "SENSEX,IDO,75000.0,2025-04-24,PE,300.0,350.0,1500,-100,600,295.0,180000.0,75200.0\n"
    )

    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = sample_bse_csv.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        result = mgr.fetch_bse_option_chain("SENSEX")
        assert result["symbol"] == "SENSEX"
        assert result["records_count"] == 1
        assert len(result["data"]) == 1
        strike_data = result["data"][0]
        assert strike_data["strikePrice"] == 75000.0
        assert strike_data["CE"]["openInterest"] == 1200
        assert strike_data["PE"]["openInterest"] == 1500
        assert strike_data["CE"]["lastPrice"] == 510.0
        assert result["expiries"] == ["2025-04-24"]

from decimal import Decimal

import pytest

from faithguard.data import edgar

INSTANCE = b"""<?xml version="1.0" encoding="utf-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
  xmlns:us-gaap="http://fasb.org/us-gaap/2024" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
  xmlns:srt="http://fasb.org/srt/2024" xmlns:dei="http://xbrl.sec.gov/dei/2024">
  <xbrli:context id="FY2025">
    <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="FY2025_Services">
    <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier>
      <xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">us-gaap:ServiceMember</xbrldi:explicitMember></xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:context id="I2025">
    <xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
  <xbrli:unit id="usdPerShare"><xbrli:divide>
    <xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>
    <xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator>
  </xbrli:divide></xbrli:unit>
  <us-gaap:Revenues contextRef="FY2025" unitRef="usd" decimals="-6">8432500000</us-gaap:Revenues>
  <us-gaap:Revenues contextRef="FY2025_Services" unitRef="usd" decimals="-6">2104000000</us-gaap:Revenues>
  <us-gaap:Assets contextRef="I2025" unitRef="usd" decimals="-6">20100000000</us-gaap:Assets>
  <us-gaap:EarningsPerShareBasic contextRef="FY2025" unitRef="usdPerShare" decimals="2">4.12</us-gaap:EarningsPerShareBasic>
  <dei:DocumentType contextRef="FY2025">10-K</dei:DocumentType>
</xbrli:xbrl>"""


def test_instance_facts_with_dimensions_periods_and_units():
    facts = edgar.parse_instance(INSTANCE, entity="0000000001")
    by = {(f.concept, f.dimensions): f for f in facts}
    total = by[("us-gaap:Revenues", ())]
    services = by[("us-gaap:Revenues", (("srt:ProductOrServiceAxis", "us-gaap:ServiceMember"),))]
    assert total.value == Decimal("8432500000") and total.period_start == "2025-01-01" and total.decimals == -6
    assert services.value == Decimal("2104000000")
    assets = by[("us-gaap:Assets", ())]
    assert assets.period_start is None and assets.period_end == "2025-12-31"
    eps = by[("us-gaap:EarningsPerShareBasic", ())]
    assert eps.unit == "USD/shares"
    assert all(f.concept != "dei:DocumentType" for f in facts)  # text facts have no unit


def test_requests_need_a_declared_user_agent(monkeypatch):
    monkeypatch.delenv("FG_SEC_USER_AGENT", raising=False)
    with pytest.raises(edgar.SecAccessError):
        edgar.user_agent()
    monkeypatch.setenv("FG_SEC_USER_AGENT", "FaithGuard research A Person a.person@example.com")
    assert "@" in edgar.user_agent()


def test_cik_padding():
    assert edgar.cik10(320193) == "0000320193"

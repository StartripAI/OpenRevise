"""Biomed source clients (PubMed via NCBI E-utilities, Europe PMC via REST, PMC via E-utilities)."""
from __future__ import annotations

from openrevise.sources.biomed.pubmed import search as pubmed_search
from openrevise.sources.biomed.europepmc import search as epmc_search
from openrevise.sources.biomed.pmc import search as pmc_search


def test_pubmed_esearch_parses_id_list(requests_mock):
    requests_mock.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        json={"esearchresult": {"idlist": ["12345", "67890"]}},
    )
    result = pubmed_search({"query": "HFrEF SGLT2", "limit": 10})
    assert [r["pmid"] for r in result] == ["12345", "67890"]


def test_europepmc_search_parses_results(requests_mock):
    requests_mock.get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        json={"resultList": {"result": [{"id": "PMC1", "title": "x"}]}},
    )
    result = epmc_search({"query": "anything"})
    assert result[0]["id"] == "PMC1"


def test_pmc_esearch_parses_id_list(requests_mock):
    requests_mock.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        json={"esearchresult": {"idlist": ["PMC123"]}},
    )
    result = pmc_search({"query": "test"})
    assert result[0]["pmcid"] == "PMC123"

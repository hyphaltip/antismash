# License: GNU Affero General Public License v3 or later
# A copy of GNU AGPL v3 should have been included in this software package in LICENSE.txt.

# for test files, silence irrelevant and noisy pylint warnings
# pylint: disable=use-implicit-booleaness-not-comparison,protected-access,missing-docstring,consider-using-with

from collections import OrderedDict
from io import StringIO
import unittest

import Bio.SeqIO as seqio
from Bio.SeqFeature import FeatureLocation, SeqFeature
from helperlibs.wrappers.io import TemporaryDirectory

from antismash.common import serialiser
from antismash.common.secmet import Record
from antismash.common.secmet.test import helpers
from antismash.common.test.helpers import DummyRecord, get_path_to_nisin_genbank


class TestResultsJSON(unittest.TestCase):
    def create_data_stream(self, data):
        def force_source_ordering(records):
            for record in records:
                source = None
                for feature in record.features:
                    if feature.type == "source":
                        source = feature
                        break
                new = OrderedDict()
                for qual in sorted(list(source.qualifiers)):
                    new[qual] = source.qualifiers[qual]
                source.qualifiers = new

        stream = StringIO()
        biopython = [rec.to_biopython() for rec in data]

        # because otherwise there's a nondeterministic ordering mismatch
        force_source_ordering(biopython)

        seqio.write(biopython, stream, "genbank")
        stream.seek(0)
        return stream

    def test_record_to_json_and_back(self):
        filename = get_path_to_nisin_genbank()
        records = list(seqio.parse(open(filename, encoding="utf-8"), "genbank"))
        records = [Record.from_biopython(rec, taxon="bacteria") for rec in records]
        rec_results = [{}, {}, {}]
        results = serialiser.AntismashResults(filename, records, rec_results, "dummy", taxon="dummytaxon")
        assert results.taxon == "dummytaxon"
        json_handle = StringIO()
        results.write_to_file(json_handle)
        json_handle.seek(0)
        new_results = serialiser.AntismashResults.from_file(json_handle)
        assert new_results.taxon == results.taxon
        assert results.to_json() == new_results.to_json()
        # check no records were lost
        assert len(new_results.records) == len(results.records)
        # check that the contents of the records is the same
        #  by converting to biopython and writing to genbanks
        original = self.create_data_stream(results.records)
        new = self.create_data_stream(new_results.records)
        oldvalue = original.getvalue()
        newvalue = new.getvalue()
        with TemporaryDirectory(change=True):
            open("old.json", "w", encoding="utf-8").write(oldvalue)
            open("new.json", "w", encoding="utf-8").write(newvalue)
            for oldline, newline in zip(oldvalue.split('\n'), newvalue.split('\n')):
                assert oldline == newline

    def test_invalid_file_raises_error(self):
        filename = get_path_to_nisin_genbank()
        self.assertRaisesRegex(ValueError, "Cannot load results to reuse",
                               serialiser.AntismashResults.from_file, filename)


class TestFeatureSerialiser(unittest.TestCase):
    def test_simple_feature(self):
        location = FeatureLocation(1, 6, strand=1)
        f_type = "test type"
        qualifiers = {"a": ["1", "2"], "b": ["3", "4"]}
        f_id = "dummy id"
        # skipping biopython deprecated members: ref, ref_db, strand, location_operator

        feature = SeqFeature(location=location, type=f_type,
                             qualifiers=qualifiers, id=f_id)
        print(str(feature))

        json = serialiser.feature_to_json(feature)
        print(json)  # for debugging failures
        new_feature = serialiser.feature_from_json(json)
        print(str(new_feature))
        assert new_feature.qualifiers == feature.qualifiers
        assert new_feature.id == feature.id
        assert new_feature.type == feature.type
        assert str(new_feature.location) == str(new_feature.location)


class TestAreas(unittest.TestCase):
    def test_empty(self):
        record = DummyRecord()
        result = serialiser.gather_record_areas(record)
        assert result == []

    def test_complex(self):
        protos = [
            helpers.DummyProtocluster(core_start=3, core_end=22, neighbourhood_range=1, product='a'),
            helpers.DummyProtocluster(core_start=33, core_end=48, neighbourhood_range=2, product='b'),
        ]
        candidates = [
            helpers.DummyCandidateCluster(clusters=protos[:1]),
            helpers.DummyCandidateCluster(clusters=protos, kind=helpers.DummyCandidateCluster.kinds.INTERLEAVED)
        ]
        subregion = helpers.DummySubRegion(start=55, end=90)
        regions = [
            helpers.DummyRegion(candidate_clusters=candidates, subregions=[]),
            helpers.DummyRegion(candidate_clusters=[], subregions=[subregion]),
        ]

        record = DummyRecord(record_id="test", seq="A"*90,
                             features=regions + [subregion] + candidates + protos)
        results = serialiser.gather_record_areas(record)
        assert results
        assert len(results) == 2
        res = results[0]
        assert res["end"] == protos[1].location.end
        assert res["products"] == [p.product for p in protos]
        assert res["subregions"] == []
        assert len(res["protoclusters"]) == 2
        assert list(res["protoclusters"]) == [0, 1]
        assert res["protoclusters"][1]["product"] == protos[1].product
        assert len(res["candidates"]) == 2
        assert res["candidates"][0]["protoclusters"] == [0]
        assert res["candidates"][1]["protoclusters"] == [0, 1]

        res = results[1]
        assert res["start"] == subregion.location.start
        assert res["subregions"]
        assert res["subregions"][0]["start"] == subregion.location.start
        assert res["subregions"][0]["tool"] == subregion.tool
        assert res["subregions"][0]["label"] == subregion.label
        assert not res["protoclusters"]

        # lastly, check all this is properly embedded in the final JSON
        bio = record.to_biopython()
        full = serialiser.dump_records([bio], [{}], [record])
        assert full[0]["areas"] == results


def test_storing_original_ids():
    records = [
        DummyRecord(seq="A"*3, record_id="A"),
        DummyRecord(seq="G"*3, record_id="B"),
    ]
    assert records[0].original_id is None
    records[1].original_id = "some really long name"
    results = serialiser.AntismashResults("dummy.gbk", records, [{}, {}], "dummy", taxon="dummytaxon")
    json_handle = StringIO()
    results.write_to_file(json_handle)
    json_handle.seek(0)
    new_results = serialiser.AntismashResults.from_file(json_handle)
    for old, new in zip(records, new_results.records):
        assert old.seq == new.seq  # a simple check that other data matches
        assert old.id == new.id
        assert old.original_id == new.original_id

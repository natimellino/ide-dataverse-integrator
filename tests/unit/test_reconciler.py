from unittest.mock import create_autospec

import pytest

from ide_dataverse_integrator.clients.dataverse import DataverseClient
from ide_dataverse_integrator.models.reconciliation import ReconciliationPlan
from ide_dataverse_integrator.services.reconciler import reconcile


@pytest.fixture
def dv_client():
    return create_autospec(DataverseClient, instance=True)


class TestReconcile:
    def test_new_uuid_goes_to_create(self, dv_client):
        dv_client.find_by_geonetwork_uuid.return_value = None

        plan = reconcile(["uuid-new"], dv_client)

        assert plan.to_create == ["uuid-new"]
        assert plan.existing == {}
        assert plan.orphans == {}

    def test_existing_uuid_goes_to_existing(self, dv_client):
        dv_client.find_by_geonetwork_uuid.return_value = "doi:10.5072/FK2/EXIST"

        plan = reconcile(["uuid-old"], dv_client)

        assert plan.to_create == []
        assert plan.existing == {"uuid-old": "doi:10.5072/FK2/EXIST"}

    def test_mixed_uuids_classified_correctly(self, dv_client):
        def _find(uuid):
            return {"uuid-a": "doi:10.5072/FK2/A"}.get(uuid)

        dv_client.find_by_geonetwork_uuid.side_effect = _find

        plan = reconcile(["uuid-a", "uuid-b", "uuid-c"], dv_client)

        assert plan.to_create == ["uuid-b", "uuid-c"]
        assert plan.existing == {"uuid-a": "doi:10.5072/FK2/A"}
        assert plan.orphans == {}

    def test_empty_discovered_returns_empty_plan(self, dv_client):
        plan = reconcile([], dv_client)

        assert plan.to_create == []
        assert plan.existing == {}
        dv_client.find_by_geonetwork_uuid.assert_not_called()

    def test_all_existing_has_no_work(self, dv_client):
        dv_client.find_by_geonetwork_uuid.return_value = "doi:10.5072/FK2/X"

        plan = reconcile(["uuid-1"], dv_client)

        assert not plan.has_work

    def test_new_uuids_has_work(self, dv_client):
        dv_client.find_by_geonetwork_uuid.return_value = None

        plan = reconcile(["uuid-1"], dv_client)

        assert plan.has_work


class TestReconciliationPlan:
    def test_has_work_with_to_create(self):
        plan = ReconciliationPlan(to_create=["uuid-1"])
        assert plan.has_work

    def test_has_work_with_orphans(self):
        plan = ReconciliationPlan(orphans={"uuid-1": "doi:10.5072/FK2/X"})
        assert plan.has_work

    def test_no_work_when_only_existing(self):
        plan = ReconciliationPlan(existing={"uuid-1": "doi:10.5072/FK2/X"})
        assert not plan.has_work

    def test_no_work_when_empty(self):
        plan = ReconciliationPlan()
        assert not plan.has_work

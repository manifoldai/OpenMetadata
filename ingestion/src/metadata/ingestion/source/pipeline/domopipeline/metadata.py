#  Copyright 2021 Collate
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""
Domo Pipeline source to extract metadata
"""
import traceback
from typing import Dict, Iterable, Optional

from metadata.generated.schema.api.data.createPipeline import CreatePipelineRequest
from metadata.generated.schema.api.lineage.addLineage import AddLineageRequest
from metadata.generated.schema.entity.data.pipeline import (
    PipelineStatus,
    StatusType,
    Task,
    TaskStatus,
)
from metadata.generated.schema.entity.services.connections.pipeline.domoPipelineConnection import (
    DomoPipelineConnection,
)
from metadata.generated.schema.metadataIngestion.workflow import (
    Source as WorkflowSource,
)
from metadata.ingestion.api.models import Either, StackTraceError
from metadata.ingestion.api.steps import InvalidSourceException
from metadata.ingestion.models.pipeline_status import OMetaPipelineStatus
from metadata.ingestion.ometa.ometa_api import OpenMetadata
from metadata.ingestion.source.pipeline.pipeline_service import PipelineServiceSource
from metadata.utils.helpers import clean_uri
from metadata.utils.logger import ingestion_logger

logger = ingestion_logger()

STATUS_MAP = {
    "success": StatusType.Successful.value,
    "failure": StatusType.Failed.value,
    "queued": StatusType.Pending.value,
}


class DomopipelineSource(PipelineServiceSource):
    """
    Implements the necessary methods to extract
    Pipeline metadata from Domo's metadata db
    """

    @classmethod
    def create(cls, config_dict, metadata: OpenMetadata):
        config = WorkflowSource.parse_obj(config_dict)
        connection: DomoPipelineConnection = config.serviceConnection.__root__.config
        if not isinstance(connection, DomoPipelineConnection):
            raise InvalidSourceException(
                f"Expected DomoPipelineConnection, but got {connection}"
            )
        return cls(config, metadata)

    def get_pipeline_name(self, pipeline_details) -> str:
        return pipeline_details["name"]

    def get_pipelines_list(self) -> Dict:
        results = self.connection.get_pipelines()
        for result in results:
            yield result

    def yield_pipeline(
        self, pipeline_details
    ) -> Iterable[Either[CreatePipelineRequest]]:
        try:
            pipeline_name = pipeline_details["id"]
            source_url = self.get_source_url(pipeline_id=pipeline_name)
            task = Task(
                name=pipeline_name,
                displayName=pipeline_details.get("name"),
                description=pipeline_details.get("description", ""),
                sourceUrl=source_url,
            )

            pipeline_request = CreatePipelineRequest(
                name=pipeline_name,
                displayName=pipeline_details.get("name"),
                description=pipeline_details.get("description", ""),
                tasks=[task],
                service=self.context.pipeline_service.fullyQualifiedName.__root__,
                startDate=pipeline_details.get("created"),
                sourceUrl=source_url,
            )
            yield Either(right=pipeline_request)
            self.register_record(pipeline_request=pipeline_request)

        except KeyError as err:
            yield Either(
                left=StackTraceError(
                    name=pipeline_details.get("name", "unknown"),
                    error=f"Error extracting data from {pipeline_details.get('name', 'unknown')} - {err}",
                    stack_trace=traceback.format_exc(),
                )
            )
        except Exception as err:
            yield Either(
                left=StackTraceError(
                    name=pipeline_details.get("name", "unknown"),
                    error=f"Wild error ingesting pipeline {pipeline_details.get('name', 'unknown')} - {err}",
                    stack_trace=traceback.format_exc(),
                )
            )

    def yield_pipeline_lineage_details(
        self, pipeline_details
    ) -> Iterable[Either[AddLineageRequest]]:
        """Lineage not implemented"""

    def yield_pipeline_status(self, pipeline_details) -> Iterable[OMetaPipelineStatus]:
        pipeline_id = pipeline_details.get("id")
        if not pipeline_id:
            logger.debug(
                f"Could not extract ID from {pipeline_details} while getting status."
            )
            return
        runs = self.connection.get_runs(pipeline_id)
        try:
            for run in runs or []:
                start_time = run["beginTime"] // 1000 if run.get("beginTime") else None
                end_time = run["endTime"] // 1000 if run.get("endTime") else None
                run_state = run.get("state", "Pending")

                task_status = TaskStatus(
                    name=pipeline_id,
                    executionStatus=STATUS_MAP.get(
                        run_state.lower(), StatusType.Pending.value
                    ),
                    startTime=start_time,
                    endTime=end_time,
                )

                pipeline_status = PipelineStatus(
                    taskStatus=[task_status],
                    executionStatus=STATUS_MAP.get(
                        run_state.lower(), StatusType.Pending.value
                    ),
                    timestamp=end_time,
                )

                yield Either(
                    right=OMetaPipelineStatus(
                        pipeline_fqn=self.context.pipeline.fullyQualifiedName.__root__,
                        pipeline_status=pipeline_status,
                    )
                )
        except Exception as err:
            yield Either(
                left=StackTraceError(
                    name=self.context.pipeline.fullyQualifiedName.__root__,
                    error=f"Error extracting status for {pipeline_id} - {err}",
                    stack_trace=traceback.format_exc(),
                )
            )

    def get_source_url(
        self,
        pipeline_id: str,
    ) -> Optional[str]:
        try:
            return (
                f"{clean_uri(self.service_connection.instanceDomain)}/datacenter/dataflows/"
                f"{pipeline_id}/details#history"
            )
        except Exception as exc:
            logger.debug(traceback.format_exc())
            logger.warning(f"Unable to get source url for {pipeline_id}: {exc}")
        return None

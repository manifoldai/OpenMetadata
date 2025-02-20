package org.openmetadata.service.dataInsight;

import java.text.ParseException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.openmetadata.schema.dataInsight.type.AggregatedUsedVsUnusedAssetsCount;

public abstract class AggregatedUsedvsUnusedAssetsCountAggregator<A, H, B, S>
    implements DataInsightAggregatorInterface {
  private final A aggregations;

  public AggregatedUsedvsUnusedAssetsCountAggregator(A aggregations) {
    this.aggregations = aggregations;
  }

  @Override
  public List<Object> aggregate() throws ParseException {
    H histogramBucket = getHistogramBucket(this.aggregations);
    List<Object> data = new ArrayList<>();
    for (B bucket : getBuckets(histogramBucket)) {
      String dateTimeString = getKeyAsString(bucket);
      Long timestamp = convertDatTimeStringToTimestamp(dateTimeString);
      S totalUnused = getAggregations(bucket, "totalUnused");
      S totalUsed = getAggregations(bucket, "totalUsed");
      Double used = Objects.requireNonNullElse(getValue(totalUsed), 0.0);
      Double unused = Objects.requireNonNullElse(getValue(totalUnused), 0.0);
      Double total = used + unused;
      Double usedPercentage = used / total;
      Double unusedPercentage = unused / total;

      data.add(
          new AggregatedUsedVsUnusedAssetsCount()
              .withTimestamp(timestamp)
              .withUnused(unused)
              .withUnusedPercentage(unusedPercentage)
              .withUsed(used)
              .withUsedPercentage(usedPercentage));
    }
    return data;
  }

  protected abstract H getHistogramBucket(A aggregations);

  protected abstract List<? extends B> getBuckets(H histogramBucket);

  protected abstract String getKeyAsString(B bucket);

  protected abstract S getAggregations(B bucket, String key);

  protected abstract Double getValue(S aggregations);
}

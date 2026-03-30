"""Reusable SparkSession factory for the E-Commerce Data Platform."""

from pyspark.sql import SparkSession


def get_spark_session(
    app_name: str = "EcommerceDataPlatform",
    master: str = "local[*]",
    enable_delta: bool = False,
) -> SparkSession:
    """
    Create or retrieve an existing SparkSession.

    Args:
        app_name:     Application name shown in the Spark Web UI.
        master:       Spark master URL.  Use "local[*]" for local runs,
                      "spark://spark-master:7077" for the Docker cluster.
        enable_delta: If True, configure Delta Lake jars and extensions.
                      Requires delta-spark installed in the Python env.

    Returns:
        Configured SparkSession.
    """
    builder = (
        SparkSession.builder.appName(app_name)
        .master(master)
        # Adaptive query execution — improves join and shuffle performance
        .config("spark.sql.adaptive.enabled", "true")
        # Keep shuffle partitions low: total dataset ~1.5M rows
        .config("spark.sql.shuffle.partitions", "8")
        # Broadcast joins for small lookup tables (< 10 MB)
        .config("spark.sql.autoBroadcastJoinThreshold", str(10 * 1024 * 1024))
        # Improve Parquet read performance
        .config("spark.sql.parquet.filterPushdown", "true")
        .config("spark.sql.parquet.mergeSchema", "false")
    )

    if enable_delta:
        builder = (
            builder
            .config(
                "spark.jars.packages",
                "io.delta:delta-spark_2.12:3.1.0",
            )
            .config(
                "spark.sql.extensions",
                "io.delta.sql.DeltaSparkSessionExtension",
            )
            .config(
                "spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog",
            )
        )

    return builder.getOrCreate()


def stop_spark(spark: SparkSession) -> None:
    """Gracefully stop the SparkSession."""
    spark.stop()

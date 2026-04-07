locals {
  alert_email_recipients = distinct(compact(concat(var.alert_emails, var.alert_email != "" ? [var.alert_email] : [])))
}

resource "google_monitoring_metric_descriptor" "model_roc_auc" {
  type         = "custom.googleapis.com/model/roc_auc"
  metric_kind  = "GAUGE"
  value_type   = "DOUBLE"
  display_name = "Model ROC-AUC"

  labels {
    key         = "project_id"
    value_type  = "STRING"
    description = "Project identifier"
  }
}

resource "google_monitoring_metric_descriptor" "data_drift_score" {
  type         = "custom.googleapis.com/data/drift_score"
  metric_kind  = "GAUGE"
  value_type   = "DOUBLE"
  display_name = "Data Drift Score"

  labels {
    key         = "project_id"
    value_type  = "STRING"
    description = "Project identifier"
  }
}

# Notification channels for email alerts
resource "google_monitoring_notification_channel" "email" {
  for_each     = toset(local.alert_email_recipients)
  display_name = "Foresight Email Notifications (${var.environment}) - ${each.value}"
  type         = "email"
  enabled      = true

  labels = {
    email_address = each.value
  }
}

# Alert Policy 1: Cloud Run API Service Failure
# Alert when API service experiences failures (error rate > 0.05)
resource "google_monitoring_alert_policy" "api_error_rate" {
  display_name = "Foresight API Error Rate High (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "Error rate > 5%"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\" AND resource.labels.service_name=\"foresight-api\" AND metric.labels.response_code_class=\"500\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [for ch in google_monitoring_notification_channel.email : ch.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "The Foresight API service error rate has exceeded 5%. Check Cloud Run logs at https://console.cloud.google.com/run/detail/${var.region}/foresight-api/logs"
    mime_type = "text/markdown"
  }

  depends_on = [google_monitoring_notification_channel.email]
}

# Alert Policy 2: Cloud Run Dashboard Service Failure
resource "google_monitoring_alert_policy" "dashboard_error_rate" {
  display_name = "Foresight Dashboard Error Rate High (${var.environment})"
  combiner     = "OR"

  conditions {
    display_name = "Error rate > 5%"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\" AND resource.labels.service_name=\"foresight-dashboard\" AND metric.labels.response_code_class=\"500\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [for ch in google_monitoring_notification_channel.email : ch.id]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "The Foresight Dashboard service error rate has exceeded 5%. Check Cloud Run logs at https://console.cloud.google.com/run/detail/${var.region}/foresight-dashboard/logs"
    mime_type = "text/markdown"
  }

  depends_on = [google_monitoring_notification_channel.email]
}

# Alert Policy 3: Model ROC-AUC Degradation
# This monitors a custom metric published by the model evaluation pipeline
resource "google_monitoring_alert_policy" "model_roc_auc_low" {
  display_name = "Model ROC-AUC Below Threshold (${var.environment})"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "ROC-AUC < 0.85"

    condition_threshold {
      filter          = "resource.type=\"global\" AND metric.type=\"custom.googleapis.com/model/roc_auc\" AND resource.labels.project_id=\"${var.project_id}\""
      duration        = "60s"
      comparison      = "COMPARISON_LT"
      threshold_value = 0.85

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [for ch in google_monitoring_notification_channel.email : ch.id]

  alert_strategy {
    auto_close = "3600s"
  }

  documentation {
    content   = "Model ROC-AUC has dropped below 0.85 threshold. This indicates potential model degradation. Review recent training runs in MLflow: ${var.enable_mlflow ? google_cloud_run_v2_service.mlflow[0].uri : "N/A"}"
    mime_type = "text/markdown"
  }

  depends_on = [
    google_monitoring_notification_channel.email,
    google_monitoring_metric_descriptor.model_roc_auc,
  ]
}

# Alert Policy 4: Data Drift Detection
# This monitors drift metrics published by the drift detection pipeline
resource "google_monitoring_alert_policy" "data_drift_detected" {
  display_name = "Data Drift Detected (${var.environment})"
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Drift metric > 0.1"

    condition_threshold {
      filter          = "resource.type=\"global\" AND metric.type=\"custom.googleapis.com/data/drift_score\" AND resource.labels.project_id=\"${var.project_id}\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.1

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = [for ch in google_monitoring_notification_channel.email : ch.id]

  alert_strategy {
    auto_close = "7200s"
  }

  documentation {
    content   = "Data drift has been detected in the production data. This may indicate that the model needs retraining. Check the monitoring dashboard for detailed drift analysis."
    mime_type = "text/markdown"
  }

  depends_on = [
    google_monitoring_notification_channel.email,
    google_monitoring_metric_descriptor.data_drift_score,
  ]
}

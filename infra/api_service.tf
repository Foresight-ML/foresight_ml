# Cloud Run Service for Foresight API
resource "google_cloud_run_v2_service" "api" {
  name     = "foresight-api"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  deletion_protection = false

  template {
    service_account = google_service_account.api.email
    timeout         = "3600s" # 1 hour timeout for long-running predictions

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.api_image

      ports {
        container_port = 8080
      }

      startup_probe {
        initial_delay_seconds = 30
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 10
        http_get {
          path = "/health"
          port = 8080
        }
      }

      liveness_probe {
        initial_delay_seconds = 60
        timeout_seconds       = 5
        period_seconds        = 30
        http_get {
          path = "/health"
          port = 8080
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }

      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.data_lake.name
      }

      env {
        name  = "MLFLOW_TRACKING_URI"
        value = var.enable_mlflow ? google_cloud_run_v2_service.mlflow[0].uri : ""
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "LOG_LEVEL"
        value = var.environment == "prod" ? "INFO" : "DEBUG"
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      launch_stage,
    ]
  }

  depends_on = [
    google_service_account.api,
  ]
}

# Allow public access to API
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

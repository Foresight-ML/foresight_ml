# Secret for API keys in Google Cloud Secret Manager
resource "google_secret_manager_secret" "api_keys" {
  secret_id = "foresight-api-keys"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    managed_by  = "terraform"
    project     = "foresight-ml"
  }
}

# Optional initial version of API keys secret (managed via Terraform variables)
resource "google_secret_manager_secret_version" "api_keys_initial" {
  count       = var.create_initial_api_keys_version ? 1 : 0
  secret      = google_secret_manager_secret.api_keys.id
  secret_data = jsonencode(var.api_keys_secret_payload)
}

# Grant API service account read access to the secret
resource "google_secret_manager_secret_iam_member" "api_keys_accessor" {
  secret_id = google_secret_manager_secret.api_keys.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

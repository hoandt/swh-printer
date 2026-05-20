import warnings

# Suppress urllib3 NotOpenSSLWarning on older system OpenSSL/LibreSSL builds
# We filter by message string to avoid importing urllib3, which triggers the warning during its own import.
warnings.filterwarnings("ignore", message=".*urllib3 v2 only supports OpenSSL.*")

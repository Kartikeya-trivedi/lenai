"""
Locust load testing configuration for LenAI API.

Run with:
  locust -f tests/locustfile.py --headless -u 20 -r 5 -t 60s --host http://localhost:8000
"""

from locust import HttpUser, between, task, tag


class LenAIUser(HttpUser):
    """Simulates a typical API user making inference requests."""

    wait_time = between(1, 3)

    def on_start(self):
        """Create an API key for this user on start."""
        # Use a pre-seeded test key or create one
        # Use the seeded development key (created by `make seed`)
        self.api_key = "lenai_sk_dev_test_key_12345678"
        self.headers = {"X-API-Key": self.api_key}

    @tag("health")
    @task(5)
    def health_check(self):
        """High-frequency health checks (simulates monitoring)."""
        self.client.get("/health")

    @tag("health")
    @task(2)
    def readiness_check(self):
        """Readiness probe."""
        self.client.get("/readiness")

    @tag("inference", "image")
    @task(3)
    def submit_image_job(self):
        """Submit an image generation job."""
        self.client.post(
            "/v1/infer/image",
            headers=self.headers,
            data={
                "prompt": "A beautiful sunset over mountains, oil painting style",
                "width": "512",
                "height": "512",
                "steps": "10",
            },
        )

    @tag("inference", "tts")
    @task(2)
    def submit_tts_job(self):
        """Submit a text-to-speech job."""
        self.client.post(
            "/v1/infer/voice_tts",
            headers=self.headers,
            data={
                "text": "Hello, this is a load test for the LenAI platform.",
                "voice": "af_bella",
                "speed": "1.0",
            },
        )

    @tag("jobs")
    @task(4)
    def list_jobs(self):
        """List jobs with pagination."""
        self.client.get(
            "/v1/jobs",
            headers=self.headers,
            params={"limit": 10, "offset": 0},
        )

    @tag("keys")
    @task(1)
    def list_api_keys(self):
        """List API keys."""
        self.client.get(
            "/v1/api-keys",
            headers=self.headers,
        )

    @tag("usage")
    @task(1)
    def get_usage(self):
        """Get usage dashboard."""
        self.client.get(
            "/v1/usage",
            headers=self.headers,
            params={"days": 30},
        )

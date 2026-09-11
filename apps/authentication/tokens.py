from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return (
            str(user.pk)
            + str(timestamp)
            + str(user.email)
            + str(user.is_verified)
            + str(user.password)
        )


email_verification_token = EmailVerificationTokenGenerator()

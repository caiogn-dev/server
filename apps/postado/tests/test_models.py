from django.test import TestCase
from apps.postado.models import PostadoClient, PostadoPack, PostadoPost


class TestPostadoModels(TestCase):
    def test_client_creation(self):
        client = PostadoClient.objects.create(
            business_name="Restaurante Teste",
            niche=PostadoClient.Niche.RESTAURANT,
            tone=PostadoClient.Tone.CASUAL,
            brand_colors=["#FF0000", "#FFFFFF"],
            email="teste@email.com",
            whatsapp="61999999999",
        )
        self.assertEqual(client.status, PostadoClient.Status.ACTIVE)
        self.assertIsNotNone(client.id)

    def test_pack_creation(self):
        client = PostadoClient.objects.create(
            business_name="Salão Teste",
            niche=PostadoClient.Niche.SALON,
            tone=PostadoClient.Tone.PROFESSIONAL,
            email="salao@email.com",
            whatsapp="61988888888",
        )
        pack = PostadoPack.objects.create(client=client, month="2026-06")
        self.assertEqual(pack.status, PostadoPack.Status.PENDING)
        self.assertEqual(pack.total_posts, 0)

    def test_post_creation(self):
        client = PostadoClient.objects.create(
            business_name="Loja Teste",
            niche=PostadoClient.Niche.STORE,
            tone=PostadoClient.Tone.LUXURY,
            email="loja@email.com",
            whatsapp="61977777777",
        )
        pack = PostadoPack.objects.create(client=client, month="2026-06")
        post = PostadoPost.objects.create(
            pack=pack,
            post_number=1,
            post_type=PostadoPost.PostType.PROMO,
        )
        self.assertEqual(post.status, PostadoPost.Status.PENDING)

    def test_pack_month_unique_per_client(self):
        from django.db import IntegrityError
        client = PostadoClient.objects.create(
            business_name="Loja Dup",
            niche=PostadoClient.Niche.STORE,
            tone=PostadoClient.Tone.CASUAL,
            email="dup@email.com",
            whatsapp="61966666666",
        )
        PostadoPack.objects.create(client=client, month="2026-06")
        with self.assertRaises(IntegrityError):
            PostadoPack.objects.create(client=client, month="2026-06")

    def test_total_posts_count(self):
        client = PostadoClient.objects.create(
            business_name="Conta Posts",
            niche=PostadoClient.Niche.RESTAURANT,
            tone=PostadoClient.Tone.CASUAL,
            email="count@email.com",
            whatsapp="61955555555",
        )
        pack = PostadoPack.objects.create(client=client, month="2026-07")
        self.assertEqual(pack.total_posts, 0)
        PostadoPost.objects.create(pack=pack, post_number=1, post_type=PostadoPost.PostType.PROMO)
        PostadoPost.objects.create(pack=pack, post_number=2, post_type=PostadoPost.PostType.PRODUCT)
        pack.refresh_from_db()
        self.assertEqual(pack.total_posts, 2)

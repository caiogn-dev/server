import logging
from celery import shared_task
from django.utils import timezone
from apps.postado.services.copy_service import CopyService
from apps.postado.services.image_service import ImageService
from apps.postado.services.drive_service import DriveService

logger = logging.getLogger(__name__)

PACK_TEMPLATES = {
    'restaurant': [
        ('promo', 'Prato do dia'),
        ('promo', 'Promoção da semana'),
        ('promo', 'Promoção delivery'),
        ('product', 'Prato destaque'),
        ('product', 'Novo item do cardápio'),
        ('testimonial', 'Depoimento cliente'),
        ('testimonial', 'Avaliação 5 estrelas'),
        ('engagement', 'Pergunta de engajamento'),
        ('engagement', 'Curiosidade culinária'),
        ('behind_scenes', 'Bastidor da cozinha'),
        ('behind_scenes', 'Equipe em ação'),
        ('date', 'Data comemorativa'),
    ],
    'salon': [
        ('promo', 'Promoção semana'),
        ('promo', 'Pacote especial'),
        ('promo', 'Promoção fidelidade'),
        ('product', 'Portfólio serviço'),
        ('product', 'Novo serviço'),
        ('testimonial', 'Antes e depois'),
        ('testimonial', 'Depoimento cliente'),
        ('engagement', 'Pergunta de engajamento'),
        ('engagement', 'Dica de cuidado'),
        ('behind_scenes', 'Bastidor do salão'),
        ('behind_scenes', 'Equipe'),
        ('date', 'Data comemorativa'),
    ],
    'store': [
        ('promo', 'Promoção relâmpago'),
        ('promo', 'Desconto semana'),
        ('promo', 'Frete grátis'),
        ('product', 'Produto destaque'),
        ('product', 'Novidade'),
        ('testimonial', 'Depoimento cliente'),
        ('testimonial', 'Avaliação produto'),
        ('engagement', 'Pergunta de engajamento'),
        ('engagement', 'Dica uso produto'),
        ('behind_scenes', 'Bastidor da loja'),
        ('behind_scenes', 'Equipe'),
        ('date', 'Data comemorativa'),
    ],
}


@shared_task(name='apps.postado.tasks.generate_pack', bind=True, max_retries=2)
def generate_pack(self, pack_id: str):
    from apps.postado.models import PostadoPack, PostadoPost

    try:
        pack = PostadoPack.objects.select_related('client').get(id=pack_id)
    except PostadoPack.DoesNotExist:
        logger.error(f"generate_pack: pack {pack_id} not found")
        return

    pack.status = PostadoPack.Status.GENERATING
    pack.save(update_fields=['status'])

    copy_svc = CopyService()
    img_svc = ImageService()
    drive_svc = DriveService()

    client_obj = pack.client
    template = PACK_TEMPLATES.get(client_obj.niche, PACK_TEMPLATES['restaurant'])

    if not client_obj.drive_folder_id:
        folder_id, _ = drive_svc.create_client_folder(client_obj.business_name)
        client_obj.drive_folder_id = folder_id
        client_obj.save(update_fields=['drive_folder_id'])

    # Fix 2: guard pre-loop Drive calls so a failure resets to PENDING and retries
    try:
        month_folder_id, month_folder_url = drive_svc.create_subfolder_with_url(
            pack.month, client_obj.drive_folder_id
        )
        # Fix 3: persist the drive folder URL on the pack
        pack.drive_folder_url = month_folder_url
        pack.save(update_fields=['drive_folder_url'])
        feed_folder = drive_svc.create_subfolder('feed', month_folder_id)
        stories_folder = drive_svc.create_subfolder('stories', month_folder_id)
    except Exception as exc:
        pack.status = PostadoPack.Status.PENDING
        pack.save(update_fields=['status'])
        raise self.retry(exc=exc)

    # Fix 1: track how many posts succeed
    success_count = 0
    for idx, (post_type, _) in enumerate(template, start=1):
        try:
            post = PostadoPost.objects.create(
                pack=pack,
                post_number=idx,
                post_type=post_type,
            )

            copy_data = copy_svc.generate(post)
            post.caption = copy_data.get('caption', '')
            post.cta = copy_data.get('cta', '')
            post.hashtags = copy_data.get('hashtags', '')

            base_img = img_svc.generate_base_image(post, post.caption)
            feed_img = img_svc.composite_feed(
                base_img,
                client_obj.business_name,
                post.caption,
                post.cta,
            )
            stories_img = img_svc.to_stories(feed_img)

            feed_bytes = img_svc.save_to_bytes(feed_img)
            stories_bytes = img_svc.save_to_bytes(stories_img)

            filename = f"post_{idx:02d}.png"
            _, feed_url = drive_svc.upload_image(feed_bytes, filename, feed_folder)
            _, stories_url = drive_svc.upload_image(stories_bytes, filename, stories_folder)

            post.feed_image_url = feed_url
            post.stories_image_url = stories_url
            post.status = PostadoPost.Status.GENERATED
            post.save()
            success_count += 1

        except Exception as e:
            logger.error(f"generate_pack: post {idx} failed for pack {pack_id}: {e}")

    # Fix 1: if all posts failed, reset to PENDING instead of advancing to REVIEW
    if success_count == 0:
        pack.status = PostadoPack.Status.PENDING
        pack.save(update_fields=['status'])
        logger.error(f"generate_pack: ALL posts failed for pack {pack_id}, resetting to PENDING")
        return

    pack.status = PostadoPack.Status.REVIEW
    pack.generated_at = timezone.now()
    pack.save(update_fields=['status', 'generated_at'])
    logger.info(f"generate_pack: pack {pack_id} ready for review ({pack.posts.count()} posts)")


@shared_task(name='apps.postado.tasks.regenerate_single_post', bind=True, max_retries=2)
def regenerate_single_post(self, post_id: str):
    from apps.postado.models import PostadoPost
    try:
        post = PostadoPost.objects.select_related('pack__client').get(id=post_id)
    except PostadoPost.DoesNotExist:
        return

    post.status = 'pending'
    post.save(update_fields=['status'])

    copy_svc = CopyService()
    img_svc = ImageService()
    drive_svc = DriveService()
    client_obj = post.pack.client

    try:
        copy_data = copy_svc.generate(post)
        post.caption = copy_data.get('caption', '')
        post.cta = copy_data.get('cta', '')
        post.hashtags = copy_data.get('hashtags', '')
        post.image_prompt = copy_data.get('image_prompt', '')
        post.save(update_fields=['caption', 'cta', 'hashtags', 'image_prompt'])

        base = img_svc.generate_base_image(post, post.caption)
        feed = img_svc.composite_feed(base, client_obj.business_name, post.caption, post.cta)
        stories = img_svc.to_stories(feed)

        folder_id = client_obj.drive_folder_id or ''
        filename = f"post_{post.post_number:02d}_regen.png"
        _, feed_url = drive_svc.upload_image(img_svc.save_to_bytes(feed), filename, folder_id)
        _, stories_url = drive_svc.upload_image(img_svc.save_to_bytes(stories), f"post_{post.post_number:02d}_stories_regen.png", folder_id)

        post.feed_image_url = feed_url
        post.stories_image_url = stories_url
        post.status = 'generated'
        post.save(update_fields=['feed_image_url', 'stories_image_url', 'status'])

    except Exception as exc:
        logger.error(f"regenerate_single_post: post {post_id} failed: {exc}")
        post.status = 'rejected'
        post.revision_notes = str(exc)
        post.save(update_fields=['status', 'revision_notes'])
        raise self.retry(exc=exc, countdown=30)

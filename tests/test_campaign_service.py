"""
Unit tests for CampaignService.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.services import CampaignService
from apps.campaigns.services.scheduler_service import SchedulerService
from apps.automation.models import ScheduledMessage
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


def _make_account(owner, name='Test Account'):
    return WhatsAppAccount.objects.create(
        owner=owner,
        name=name,
        phone_number='+5511999990001',
        phone_number_id='1234567890',
        waba_id='waba_001',
        is_active=True,
    )


class CampaignServiceCreateTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='camp_owner', email='camp@example.com', password='pass'
        )
        self.account = _make_account(self.user)
        self.service = CampaignService()

    def test_create_campaign_draft(self):
        campaign = self.service.create_campaign(
            account_id=str(self.account.id),
            name='Black Friday Campaign',
            message_content={'type': 'text', 'text': 'Oferta especial!'},
            created_by=self.user,
        )
        self.assertIsNotNone(campaign.pk)
        self.assertEqual(campaign.status, Campaign.CampaignStatus.DRAFT)
        self.assertEqual(campaign.account, self.account)

    def test_create_campaign_with_recipients(self):
        contact_list = [
            {'phone': '+5511111111111', 'name': 'Alice'},
            {'phone': '+5522222222222', 'name': 'Bob'},
        ]
        campaign = self.service.create_campaign(
            account_id=str(self.account.id),
            name='Test Campaign',
            contact_list=contact_list,
            created_by=self.user,
        )
        self.assertEqual(campaign.total_recipients, 2)
        recipients = CampaignRecipient.objects.filter(campaign=campaign)
        self.assertEqual(recipients.count(), 2)

    def test_update_campaign_name(self):
        campaign = self.service.create_campaign(
            account_id=str(self.account.id),
            name='Old Name',
            created_by=self.user,
        )
        updated = self.service.update_campaign(str(campaign.id), name='New Name')
        self.assertEqual(updated.name, 'New Name')

    def test_cannot_update_running_campaign(self):
        campaign = self.service.create_campaign(
            account_id=str(self.account.id),
            name='Running',
            created_by=self.user,
        )
        campaign.status = Campaign.CampaignStatus.RUNNING
        campaign.save()

        with self.assertRaises(ValueError):
            self.service.update_campaign(str(campaign.id), name='Changed')

    def test_schedule_campaign_in_future(self):
        campaign = self.service.create_campaign(
            account_id=str(self.account.id),
            name='Scheduled Campaign',
            created_by=self.user,
        )
        future = timezone.now() + timedelta(hours=2)
        scheduled = self.service.schedule_campaign(str(campaign.id), scheduled_at=future)
        self.assertEqual(scheduled.status, Campaign.CampaignStatus.SCHEDULED)
        self.assertEqual(scheduled.scheduled_at, future)

    def test_cannot_schedule_in_past(self):
        campaign = self.service.create_campaign(
            account_id=str(self.account.id),
            name='Past Campaign',
            created_by=self.user,
        )
        past = timezone.now() - timedelta(hours=1)
        with self.assertRaises(ValueError):
            self.service.schedule_campaign(str(campaign.id), scheduled_at=past)

    def test_create_campaign_missing_account_raises(self):
        with self.assertRaises(WhatsAppAccount.DoesNotExist):
            self.service.create_campaign(
                account_id='00000000-0000-0000-0000-000000000000',
                name='Ghost Campaign',
            )


class SchedulerServiceMediaTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='scheduler_owner', email='scheduler@example.com', password='pass'
        )
        self.account = _make_account(self.user, name='Scheduler Account')
        self.service = SchedulerService()

    def test_media_url_image_content_is_scheduled_as_image(self):
        scheduled = self.service.schedule_message(
            account_id=str(self.account.id),
            to_number='556399999999',
            scheduled_at=timezone.now() + timedelta(hours=1),
            message_type=ScheduledMessage.MessageType.TEXT,
            content={
                'text': 'Oferta com foto',
                'media_url': 'https://cdn.example.com/campanha.jpg',
                'media_type': 'image',
                'filename': 'campanha.jpg',
            },
            created_by=self.user,
        )

        self.assertEqual(scheduled.message_type, ScheduledMessage.MessageType.IMAGE)
        self.assertEqual(scheduled.media_url, 'https://cdn.example.com/campanha.jpg')
        self.assertEqual(scheduled.message_text, 'Oferta com foto')

    def test_media_url_document_content_is_scheduled_as_document(self):
        scheduled = self.service.schedule_message(
            account_id=str(self.account.id),
            to_number='556388888888',
            scheduled_at=timezone.now() + timedelta(hours=1),
            message_type=ScheduledMessage.MessageType.TEXT,
            content={
                'caption': 'Cardapio em PDF',
                'media_url': 'https://cdn.example.com/cardapio.pdf',
                'media_type': 'document',
                'filename': 'cardapio.pdf',
            },
            created_by=self.user,
        )

        self.assertEqual(scheduled.message_type, ScheduledMessage.MessageType.DOCUMENT)
        self.assertEqual(scheduled.media_url, 'https://cdn.example.com/cardapio.pdf')
        self.assertEqual(scheduled.message_text, 'Cardapio em PDF')

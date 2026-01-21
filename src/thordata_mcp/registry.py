"""
Thordata Spider Registry (Ported from RAG Pipeline)
"""
from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class SpiderConfig:
    id: str
    name: str          # domain name
    desc: str          # Description
    input_key: str = "url"  # Main parameter name
    extra_params: Dict[str, Any] = field(default_factory=dict)
    is_video: bool = False  # True = /video_builder, False = /builder

# === 45+ Tools Master Registry ===
SPIDER_REGISTRY = {
    # === Amazon (5 Tools) ===
    "amazon_asin": SpiderConfig("amazon_product_by-asin", "amazon.com", "Amazon Product (ASIN)", "asin"),
    "amazon_product": SpiderConfig("amazon_global-product_by-url", "amazon.com", "Amazon Product (URL)"),
    "amazon_review": SpiderConfig("amazon_comment_by-url", "amazon.com", "Amazon Reviews"),
    "amazon_search": SpiderConfig("amazon_product-list_by-keywords-domain", "amazon.com", "Amazon Search", input_key="keyword", extra_params={"page_turning": "1"}),
    "amazon_seller": SpiderConfig("amazon_seller_by-url", "amazon.com", "Amazon Seller"),

    # === Google (5 Tools) ===
    "gmaps_detail": SpiderConfig("google_map-details_by-url", "google.com", "Google Maps Details"),
    "gmaps_review": SpiderConfig("google_comment_by-url", "google.com", "Google Maps Reviews"),
    "google_shopping": SpiderConfig("google_shopping_by-url", "google.com", "Google Shopping"),
    "play_store_app": SpiderConfig("google-play-store_information_by-url", "play.google.com", "Play Store App Info", "app_url"),
    "play_store_review": SpiderConfig("google-play-store_reviews_by-url", "play.google.com", "Play Store Reviews", "app_url"),

    # === TikTok (4 Tools) ===
    "tiktok_comment": SpiderConfig("tiktok_comment_by-url", "tiktok.com", "TikTok Comments", "url"),
    "tiktok_post": SpiderConfig("tiktok_posts_by-url", "tiktok.com", "TikTok Video Post", "post_url", is_video=True),
    "tiktok_shop": SpiderConfig("tiktok_shop_by-url", "tiktok.com", "TikTok Shop"),
    "tiktok_profile": SpiderConfig("tiktok_profiles_by-url", "tiktok.com", "TikTok Profile", "profile_url"),

    # === YouTube (7 Tools) ===
    "youtube_video": SpiderConfig("youtube_video_by-url", "youtube.com", "YouTube Video File", is_video=True),
    "youtube_channel": SpiderConfig("youtube_video-post_by-url", "youtube.com", "YouTube Channel Posts"),
    "youtube_audio": SpiderConfig("youtube_audio_by-url", "youtube.com", "YouTube Audio File", is_video=True),
    "youtube_profile_search": SpiderConfig("youtube_profiles_by-keyword", "youtube.com", "YouTube Profile Search", "keyword"),
    "youtube_transcript": SpiderConfig("youtube_transcript_by-id", "youtube.com", "YouTube Transcript", "video_id"),
    "youtube_product": SpiderConfig("youtube_product_by-id", "youtube.com", "YouTube Product", "video_id"),
    "youtube_comment": SpiderConfig("youtube_comment_by-id", "youtube.com", "YouTube Comments", "video_id"),

    # === Reddit (2 Tools) ===
    "reddit_post": SpiderConfig("reddit_posts_by-url", "reddit.com", "Reddit Post"),
    "reddit_comment": SpiderConfig("reddit_comment_by-url", "reddit.com", "Reddit Comments"),

    # === LinkedIn (2 Tools) ===
    "linkedin_company": SpiderConfig("linkedin_company_information_by-url", "linkedin.com", "LinkedIn Company"),
    "linkedin_job": SpiderConfig("linkedin_job_listings_information_by-job-listing-url", "linkedin.com", "LinkedIn Job", "job_listing_url"),

    # === Instagram (4 Tools) ===
    "ins_post": SpiderConfig("ins_posts_by-profileurl", "instagram.com", "Instagram Profile Posts", "profileurl"),
    "ins_profile": SpiderConfig("ins_profiles_by-username", "instagram.com", "Instagram Profile Info", "username"),
    "ins_reel": SpiderConfig("ins_reel_by-url", "instagram.com", "Instagram Reel", is_video=True),
    "ins_comment": SpiderConfig("ins_comment_by-posturl", "instagram.com", "Instagram Comments", "posturl"),

    # === Facebook (2 Tools) ===
    "facebook_search": SpiderConfig("facebook_post_by-keywords", "facebook.com", "Facebook Search", "keyword"),
    "facebook_post": SpiderConfig("facebook_post_by-posts-url", "facebook.com", "Facebook Post"),

    # === Twitter (2 Tools) ===
    "twitter_profile": SpiderConfig("twitter_profiles_by-url", "x.com", "Twitter Profile"),
    "twitter_post": SpiderConfig("twitter_by-posturl_by-url", "x.com", "Twitter Post", "posturl"),

    # === GitHub (1 Tool) ===
    "github_repo": SpiderConfig("github_repository_by-repo-url", "github.com", "GitHub Repository", "repo_url"),

    # === Zillow/Booking ......===
    #"zillow_property": SpiderConfig("zillow_property_details_information", "zillow.com", "Zillow Property"),
    #"booking_hotel": SpiderConfig("booking_hotel_information", "booking.com", "Booking Hotel"),
}
"""PDF password detection and decryption for password-protected documents.

Israeli insurance companies and banks commonly send password-protected PDFs
where the password is the policyholder's phone number or ID number.

This module:
  1. Detects if a PDF is encrypted
  2. Tries common passwords (family member phones, ID numbers)
  3. Returns decrypted bytes or None if all attempts fail
"""
from __future__ import annotations

import io
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def is_pdf_encrypted(file_path: str) -> bool:
    """Check if a PDF file is encrypted/password-protected."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        return reader.is_encrypted
    except Exception:
        # If we can't even read it, assume it might be encrypted
        return False


def _try_decrypt_with_password(file_path: str, password: str) -> Optional[bytes]:
    """Try to decrypt a PDF with a given password. Returns decrypted bytes or None."""
    try:
        from pypdf import PdfReader, PdfWriter
        reader = PdfReader(file_path)
        if not reader.is_encrypted:
            with open(file_path, "rb") as f:
                return f.read()
        result = reader.decrypt(password)
        if result == 0:
            return None  # wrong password
        # Write decrypted PDF to bytes
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()
    except Exception as exc:
        logger.debug("pdf_decryptor: password attempt failed: %s", exc)
        return None


def _generate_phone_variants(phone: str) -> list[str]:
    """Generate common password variants from a phone number.

    Israeli insurance companies use various formats:
    - 0542364393 (local format)
    - 972542364393 (international without +)
    - +972542364393 (international with +)
    - 542364393 (without leading 0)
    """
    digits = "".join(c for c in phone if c.isdigit())
    variants: list[str] = [digits]

    if digits.startswith("972") and len(digits) >= 12:
        local = "0" + digits[3:]
        variants.append(local)
        variants.append(digits[3:])  # without 0 or 972
        variants.append("+" + digits)
    elif digits.startswith("0") and len(digits) == 10:
        variants.append("972" + digits[1:])
        variants.append("+972" + digits[1:])
        variants.append(digits[1:])
    else:
        variants.append(digits)

    return list(dict.fromkeys(variants))  # dedupe preserving order


def build_password_candidates(
    uploader_phone: str | None = None,
    family_phones: list[str] | None = None,
    extra_passwords: list[str] | None = None,
) -> list[str]:
    """Build an ordered list of password candidates to try.

    Priority:
    1. Empty password (some PDFs have owner-only protection)
    2. Uploader's phone variants
    3. Other family member phone variants
    4. Extra passwords (ID numbers, etc.)
    """
    candidates: list[str] = [""]  # empty password first

    if uploader_phone:
        candidates.extend(_generate_phone_variants(uploader_phone))

    if family_phones:
        for phone in family_phones:
            candidates.extend(_generate_phone_variants(phone))

    if extra_passwords:
        candidates.extend(extra_passwords)

    return list(dict.fromkeys(candidates))  # dedupe preserving order


def try_decrypt_pdf(
    file_path: str,
    passwords: list[str],
) -> tuple[Optional[bytes], Optional[str]]:
    """Try to decrypt a PDF with a list of passwords.

    Returns (decrypted_bytes, successful_password) or (None, None) if all fail.
    """
    if not is_pdf_encrypted(file_path):
        with open(file_path, "rb") as f:
            return f.read(), None

    logger.info(
        "pdf_decryptor: PDF is encrypted, trying %d passwords for %s",
        len(passwords), os.path.basename(file_path),
    )

    for pwd in passwords:
        result = _try_decrypt_with_password(file_path, pwd)
        if result is not None:
            display_pwd = pwd[:3] + "***" if len(pwd) > 3 else "***"
            logger.info(
                "pdf_decryptor: decrypted %s with password %s",
                os.path.basename(file_path), display_pwd,
            )
            return result, pwd

    logger.warning(
        "pdf_decryptor: all %d passwords failed for %s",
        len(passwords), os.path.basename(file_path),
    )
    return None, None

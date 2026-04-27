"""
Domain Classifier.

Tags each file with the *concerns* it touches based on what it imports —
"this file talks to the database AND the UI AND the network."

Files that span 3+ unrelated domains are doing too many things at once.
That's the "God Object knows about DB, UI, and HTTP" code smell, but
detected from the imports rather than vibes.

The mapping is intentionally cross-language: `requests` (Python) and
`axios` (JS) and `reqwest` (Rust) all classify as `network`. Adding a
new entry only requires picking a domain, not a language.
"""

from __future__ import annotations

from brahm_kosh.models import FileModel, Project


# ---------------------------------------------------------------------------
# Domain → list of canonical import roots
# Maintained by hand. Cross-language. Add entries as needed; the order of
# entries inside a domain doesn't matter, but each name is checked as a
# normalized prefix match.
# ---------------------------------------------------------------------------

_DOMAIN_TABLE: dict[str, list[str]] = {
    "database": [
        # Python
        "sqlalchemy", "psycopg2", "psycopg", "pymongo", "redis", "mysql",
        "sqlite3", "asyncpg", "aiomysql", "motor", "tortoise", "peewee",
        "django.db", "flask_sqlalchemy", "supabase", "prisma",
        # JS/TS
        "mongoose", "sequelize", "typeorm", "knex", "drizzle", "kysely",
        "pg", "mysql2", "@prisma", "@supabase", "ioredis",
        # Java/Kotlin
        "java.sql", "jakarta.persistence", "javax.persistence", "hibernate",
        "jpa", "jdbi", "jdbc", "androidx.room",
        # Go
        "database/sql", "gorm.io", "github.com/jmoiron/sqlx",
        "github.com/jackc/pgx", "ent",
        # Rust
        "diesel", "sqlx", "tokio_postgres", "rusqlite", "mongodb",
        # C#
        "System.Data", "EntityFramework", "Microsoft.EntityFrameworkCore",
        "Dapper", "MongoDB.Driver",
        # PHP
        "PDO", "Doctrine", "Eloquent", "Illuminate\\Database",
        # Dart
        "sqflite", "drift", "hive",
        # R
        "DBI", "RSQLite", "RPostgres",
    ],
    "ui": [
        # JS/TS
        "react", "react-dom", "react-native", "vue", "svelte", "solid-js",
        "preact", "lit", "lit-html", "angular", "@angular", "ember",
        "next", "nuxt", "remix", "gatsby", "astro", "qwik",
        "jquery", "three", "three.js", "d3", "chart.js", "echarts",
        "@mui", "@chakra-ui", "@mantine", "@radix-ui", "tailwindcss",
        # Python
        "tkinter", "PyQt5", "PyQt6", "PySide6", "kivy", "flet", "rich",
        "textual", "blessed", "curses", "streamlit", "dash", "gradio",
        # Java/Kotlin
        "javafx", "android", "androidx.compose", "androidx.appcompat",
        "swing", "javax.swing",
        # C#
        "WPF", "Xamarin", "MAUI", "WinForms", "Avalonia", "Blazor",
        # Dart/Flutter
        "flutter", "package:flutter",
        # Rust
        "egui", "iced", "yew", "leptos", "dioxus", "tauri",
        # Go
        "fyne", "gioui", "gotk3",
        # Swift
        "SwiftUI", "UIKit",
    ],
    "network": [
        # Python
        "requests", "httpx", "urllib", "urllib2", "urllib3", "aiohttp",
        "websocket", "websockets", "grpc", "fastapi", "flask", "django",
        "tornado", "starlette", "uvicorn", "gunicorn", "socket", "ssl",
        # JS/TS
        "axios", "node-fetch", "got", "superagent", "ky", "wretch",
        "express", "koa", "hapi", "fastify", "nestjs", "@nestjs",
        "ws", "socket.io", "graphql", "apollo", "trpc", "@trpc",
        # Java/Kotlin
        "java.net", "java.net.http", "okhttp", "retrofit", "ktor",
        "spring.web", "spring-web", "javax.ws.rs", "jakarta.ws.rs",
        # Go
        "net/http", "github.com/gin-gonic", "github.com/labstack",
        "github.com/gofiber", "google.golang.org/grpc",
        # Rust
        "reqwest", "hyper", "actix-web", "rocket", "axum", "warp", "tonic",
        # C#
        "System.Net", "HttpClient", "ASP.NET", "Microsoft.AspNetCore",
        # PHP
        "GuzzleHttp", "Symfony\\HttpClient", "Symfony\\HttpFoundation",
        # Dart
        "dart:io", "package:http", "package:dio",
        # R
        "httr", "curl",
    ],
    "io": [
        # Python
        "os", "os.path", "pathlib", "shutil", "glob", "io", "tempfile",
        "fileinput", "fnmatch", "csv", "json", "pickle", "shelve",
        # JS/TS
        "fs", "fs/promises", "node:fs", "path", "node:path", "stream",
        "readline",
        # Java/Kotlin
        "java.io", "java.nio", "kotlin.io",
        # Go
        "io", "io/ioutil", "os", "path", "path/filepath", "bufio",
        # Rust
        "std::fs", "std::io", "std::path",
        # C#
        "System.IO",
        # Dart
        "dart:io",
    ],
    "compute": [
        # Python
        "numpy", "scipy", "pandas", "polars", "sympy", "scikit-learn",
        "sklearn", "tensorflow", "torch", "jax", "xgboost", "lightgbm",
        "statsmodels", "matplotlib", "seaborn", "plotly", "bokeh",
        # JS/TS
        "mathjs", "ml-matrix", "tensorflow", "@tensorflow",
        # R
        "dplyr", "ggplot2", "tidyr", "tibble", "purrr", "data.table",
        # Rust / C++
        "ndarray", "nalgebra", "Eigen", "blas", "lapack",
    ],
    "auth": [
        # Python
        "passlib", "bcrypt", "argon2", "jwt", "PyJWT", "authlib",
        "django.contrib.auth", "flask_login", "fastapi.security",
        # JS/TS
        "passport", "jsonwebtoken", "@auth", "next-auth", "lucia", "clerk",
        "@clerk", "firebase/auth",
        # Java
        "spring.security", "spring-security",
        # PHP
        "Illuminate\\Auth", "Symfony\\Security",
    ],
    "crypto": [
        # bcrypt/argon2/jwt are intentionally in `auth` instead — they're
        # password/token primitives, more useful flagged as auth concerns.
        "cryptography", "hashlib", "secrets", "Crypto", "nacl",
        "crypto",  # node
        "node:crypto", "openssl",
        "java.security", "javax.crypto", "javax.security",
        "System.Security.Cryptography",
        "ring", "rsa", "sha2", "openssl-sys",
    ],
    "testing": [
        "pytest", "unittest", "doctest", "mock", "hypothesis", "nose",
        "jest", "vitest", "mocha", "chai", "sinon", "@testing-library",
        "cypress", "playwright", "puppeteer",
        "junit", "org.junit", "mockito", "testng",
        "testing", "go-cmp",  # Go
        "rstest", "mockall",  # Rust
        "xunit", "nunit", "moq",  # C#
    ],
    "config": [
        "configparser", "dotenv", "python-dotenv", "yaml", "pyyaml",
        "toml", "tomllib", "tomli", "pydantic.settings", "dynaconf",
        "dotenv", "config", "conf", "node-config",
        "viper",  # Go
        "serde_yaml", "config-rs",  # Rust
    ],
    "logging": [
        "logging", "loguru", "structlog", "logfire", "sentry_sdk",
        "winston", "pino", "bunyan", "@sentry",
        "log4j", "org.slf4j", "logback",
        "log/slog", "go.uber.org/zap", "github.com/sirupsen/logrus",
        "log", "tracing", "env_logger",  # Rust
        "Microsoft.Extensions.Logging", "Serilog",  # C#
    ],
}


# Build the reverse lookup once at import time. Keys are lowercased.
_INDEX: dict[str, str] = {}
for domain, names in _DOMAIN_TABLE.items():
    for n in names:
        _INDEX[n.lower()] = domain

# Sort for prefix matching — longer prefixes match first.
_PREFIXES = sorted(_INDEX.keys(), key=len, reverse=True)


def classify_import(raw: str) -> str | None:
    """Return the domain for one raw import, or None if uncategorized."""
    if not raw:
        return None
    lower = raw.strip().lower()
    if not lower:
        return None
    # Exact match first
    if lower in _INDEX:
        return _INDEX[lower]
    # Then prefix match — `requests.adapters` should match `requests`.
    for prefix in _PREFIXES:
        if lower.startswith(prefix + ".") or lower.startswith(prefix + "/") or lower.startswith(prefix + ":") or lower.startswith(prefix + "\\"):
            return _INDEX[prefix]
    return None


def classify_file(file_model: FileModel) -> set[str]:
    """Set of domains this file's imports collectively touch."""
    domains: set[str] = set()
    for raw in file_model.raw_imports:
        d = classify_import(raw)
        if d:
            domains.add(d)
    # Internal imports almost never match the domain table by name, so we
    # don't bother filtering raws against `dependencies` — kept simple.
    return domains


def annotate_project(project: Project) -> None:
    """Populate `FileModel.domains` for every file."""
    for fm in project.all_files():
        fm.domains = classify_file(fm)


def cross_cutting_files(project: Project, threshold: int = 3) -> list[dict]:
    """
    Files whose imports span >= `threshold` distinct domains. These are
    probably doing too many things at once — the "God Object" pattern
    detected by topic rather than line count.
    """
    out = []
    for fm in project.all_files():
        if not fm.domains:
            continue
        if len(fm.domains) >= threshold:
            out.append({
                "file": fm.relative_path,
                "domains": sorted(fm.domains),
                "domain_count": len(fm.domains),
                "suggestion": (
                    f"This file mixes {len(fm.domains)} concerns "
                    f"({', '.join(sorted(fm.domains))}). "
                    f"Consider splitting along domain boundaries."
                ),
            })
    out.sort(key=lambda x: -x["domain_count"])
    return out

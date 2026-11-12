# ShopSense — Full-Stack E-Commerce Marketplace

A production-ready, full-stack e-commerce marketplace built with Django and PostgreSQL, inspired by Amazon and Myntra. This is Phase 1 of the project, implementing authentication, admin dashboard foundation, and vendor onboarding.

## Features Implemented (Phase 1)

### Authentication System
- **Custom User Model**: Email-based authentication (no username)
- **Secure Login/Logout**: CSRF protection, rate limiting, account locking
- **Password Management**: Strong validation, reset via email, secure hashing (PBKDF2)
- **Registration**: Role selection (Admin, Vendor, Customer)
- **Profile Management**: View and edit personal information

### Admin Dashboard
- **Responsive Sidebar Navigation**: Collapsible, mobile-friendly
- **Real-time Statistics**: Vendors, products, orders, revenue
- **Recent Activity Feed**: Audit log of administrative actions
- **Pending Approvals**: Quick access to vendor applications needing review
- **Quick Actions**: Invite vendors, review applications, manage users

### Vendor Onboarding
- **Public Application Form**: Business details, contact info, address, tax ID
- **Auto-generated Vendor IDs**: Format `VNDXXXXXXXX`
- **Status Tracking**: Pending → Approved/Rejected/More Info
- **Admin Review Actions**: Approve, reject, request more info with notes
- **Audit Trail**: Complete history of all vendor application actions

### Role-Based Access Control
- **Admin**: Full marketplace management
- **Vendor**: Own profile, products, inventory (future phases)
- **Customer**: Browse, cart, orders (future phases)
- **Server-side enforcement**: Not just UI hiding

### Security Features
- **CSRF Protection**: On all forms
- **Rate Limiting**: django-axes (5 attempts, 15-min lockout)
- **Content Security Policy**: django-csp headers
- **Secure Cookies**: HttpOnly, SameSite, Secure (production)
- **Password Validation**: 10+ chars, uppercase, lowercase, digit, special char
- **SQL Injection Prevention**: Django ORM only
- **XSS Protection**: Template auto-escaping, CSP

### Technical Stack
- **Backend**: Django 5.0
- **Database**: PostgreSQL (Supabase)
- **Frontend**: Django Templates, HTML5, CSS3, Vanilla JS
- **Icons**: Lucide (CDN)
- **Fonts**: Inter (Google Fonts)
- **Environment**: python-dotenv / django-environ
- **Testing**: pytest, pytest-django, factory-boy

## Project Structure

```
shopsense/
├── config/                 # Django project settings
│   ├── settings.py         # Main settings
│   ├── urls.py             # Root URL configuration
│   ├── wsgi.py             # WSGI entry point
│   └── views.py            # Error handlers
├── accounts/               # User authentication
│   ├── models.py           # Custom User model
│   ├── forms.py            # Login, registration, password forms
│   ├── views.py            # Auth views
│   ├── urls.py             # Auth URLs
│   ├── admin.py            # Admin config
│   └── validators.py       # Custom password validator
├── vendors/                # Vendor management
│   ├── models.py           # VendorApplication, VendorProfile, AuditLog
│   ├── forms.py            # Application, profile forms
│   ├── views.py            # Onboarding, admin views
│   ├── urls.py             # Vendor URLs
│   └── admin.py            # Admin config
├── dashboard/              # Admin dashboard
│   ├── views.py            # Dashboard, settings, reports
│   └── urls.py             # Dashboard URLs
├── catalog/                # Product catalog (Phase 2+)
├── orders/                 # Order management (Phase 2+)
├── templates/
│   ├── base.html           # Base template
│   ├── accounts/           # Auth templates
│   ├── dashboard/          # Dashboard templates
│   ├── vendors/            # Vendor templates
│   ├── registration/       # Password reset templates
│   └── errors/             # 404, 500 pages
├── static/
│   ├── css/
│   │   ├── base.css        # Design tokens, reset
│   │   ├── components.css  # Buttons, forms, cards, tables
│   │   ├── dashboard.css   # Dashboard layout
│   │   └── auth.css        # Auth pages
│   └── js/
│       └── main.js         # Common utilities
├── media/                  # User uploads
├── tests/                  # Automated tests
│   ├── conftest.py         # Pytest fixtures
│   ├── test_authentication.py
│   ├── test_vendors.py
│   └── test_dashboard.py
├── requirements.txt
├── .env.example
├── .env                    # Local config (not committed)
├── .gitignore
└── manage.py
```

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 14+ (or Supabase account)
- Git

### Installation

1. **Clone and enter the project**
```bash
git clone <repository-url>
cd shopsense
```

2. **Create virtual environment**
```bash
python -m venv .venv
# Windows
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your settings:
# - SECRET_KEY (generate with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
# - Database credentials (Supabase or local PostgreSQL)
# - Email settings (for password reset)
```

5. **Run migrations**
```bash
python manage.py migrate
```

6. **Create admin user**
```bash
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from accounts.models import User
User.objects.create_superuser('admin@shopsense.local', 'Admin@123!', first_name='Admin', last_name='User')
print('Superuser created')
"
```

7. **Run development server**
```bash
python manage.py runserver
```

8. **Access the application**
- Admin Dashboard: http://127.0.0.1:8000/
- Login: http://127.0.0.1:8000/accounts/login/
- Vendor Onboarding: http://127.0.0.1:8000/vendors/onboarding/

### Supabase Database Setup

1. Create a Supabase project at https://supabase.com
2. Go to Settings → Database → Connection pooling
3. Use the **Transaction pooler** (port 5432) connection string
4. Update `.env` with:
   ```env
   DB_NAME=postgres
   DB_USER=postgres.<project-ref>
   DB_PASSWORD=<your-database-password>
   DB_HOST=aws-0-<region>.pooler.supabase.com
   DB_PORT=5432
   ```

## Design System

### Colors
- **Primary**: Indigo (`#4f46e5`) - actions, links, focus states
- **Success**: Green (`#22c55e`) - approved, active
- **Warning**: Amber (`#f59e0b`) - pending, attention
- **Error**: Red (`#ef4444`) - rejected, errors
- **Neutral**: Gray scale for text, borders, backgrounds

### Typography
- **Font**: Inter (400, 500, 600, 700)
- **Scale**: xs(12px) → sm(14px) → base(16px) → lg(18px) → xl(20px) → 2xl(24px) → 3xl(30px) → 4xl(36px)

### Spacing
- **Scale**: 1(4px) → 2(8px) → 3(12px) → 4(16px) → 5(20px) → 6(24px) → 8(32px) → 10(40px) → 12(48px) → 16(64px)

### Components
- Buttons: Primary, Secondary, Outline, Ghost, Error, Success
- Forms: Inputs, Selects, Textareas, File inputs, Checkboxes, Radios
- Cards: Header, Body, Footer
- Tables: Sortable, hoverable, responsive
- Badges: Status indicators
- Modals, Dropdowns, Tooltips
- Alerts, Pagination, Tabs

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=accounts --cov=vendors --cov=dashboard

# Run specific test module
pytest tests/test_authentication.py -v
```

## Future Phases (Planned)

### Phase 2: Catalog & Products
- Category management (hierarchical)
- Product CRUD with variants
- Image galleries
- Inventory tracking
- SEO fields

### Phase 3: Orders & Checkout
- Shopping cart
- Multi-vendor checkout
- Order management
- Payment integration (Razorpay, Stripe)
- Shipping calculation

### Phase 4: Customer Experience
- Customer dashboard
- Wishlist, reviews
- Order tracking
- Notifications

### Phase 5: Analytics & Reports
- Sales dashboards
- Vendor analytics
- Export functionality
- Real-time metrics

## Security Checklist

- [x] Custom user model with email authentication
- [x] Strong password policy
- [x] CSRF protection on all forms
- [x] Rate limiting on auth endpoints
- [x] Secure password hashing (PBKDF2)
- [x] Account lockout after failed attempts
- [x] Secure session configuration
- [x] CSP headers
- [x] X-Frame-Options: DENY
- [x] SQL injection prevention (ORM)
- [x] XSS protection (template escaping)
- [x] Secure file upload handling
- [x] Environment-based secrets
- [x] Audit logging for sensitive actions

## Development Guidelines

### Code Style
- Follow PEP 8
- Use type hints
- Docstrings for public methods
- Keep functions small and focused

### Git Workflow
- Feature branches from `main`
- Descriptive commit messages
- PR reviews required
- Tests must pass

### Database Migrations
- Always create migrations after model changes
- Review generated SQL
- Test migrations on copy of production data

## License

MIT License - see LICENSE file for details.

## Support

For questions or issues, please open a GitHub issue or contact the development team.
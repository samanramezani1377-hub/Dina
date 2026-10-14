-- Guard tenant ownership at the database boundary, including direct SQL writes.
-- Application-level checks remain useful for clear errors, but they are not a
-- substitute for durable constraints when several API paths write the same data.

CREATE OR REPLACE FUNCTION dina_guard_journal_line_tenant()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    entry_org BIGINT;
    account_org BIGINT;
BEGIN
    SELECT organization_id INTO entry_org
      FROM journal_entries WHERE id = NEW.journal_entry_id;
    SELECT organization_id INTO account_org
      FROM accounts WHERE id = NEW.account_id;

    IF entry_org IS NULL OR account_org IS NULL THEN
        RAISE EXCEPTION 'journal line references a missing entry or account'
            USING ERRCODE = '23503';
    END IF;
    IF entry_org <> account_org THEN
        RAISE EXCEPTION 'journal entry and account must belong to the same organization'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_journal_lines_tenant_guard ON journal_lines;
CREATE TRIGGER trg_journal_lines_tenant_guard
BEFORE INSERT OR UPDATE OF journal_entry_id, account_id ON journal_lines
FOR EACH ROW EXECUTE FUNCTION dina_guard_journal_line_tenant();


CREATE OR REPLACE FUNCTION dina_guard_stock_movement_tenant()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    product_org BIGINT;
    warehouse_org BIGINT;
BEGIN
    SELECT organization_id INTO product_org FROM products WHERE id = NEW.product_id;
    SELECT organization_id INTO warehouse_org FROM warehouses WHERE id = NEW.warehouse_id;

    IF product_org IS NULL OR warehouse_org IS NULL THEN
        RAISE EXCEPTION 'stock movement references a missing product or warehouse'
            USING ERRCODE = '23503';
    END IF;
    IF NEW.organization_id <> product_org OR NEW.organization_id <> warehouse_org THEN
        RAISE EXCEPTION 'stock movement, product and warehouse must belong to the same organization'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_stock_movements_tenant_guard ON stock_movements;
CREATE TRIGGER trg_stock_movements_tenant_guard
BEFORE INSERT OR UPDATE OF organization_id, product_id, warehouse_id ON stock_movements
FOR EACH ROW EXECUTE FUNCTION dina_guard_stock_movement_tenant();


CREATE OR REPLACE FUNCTION dina_guard_sale_line_tenant()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    sale_org BIGINT;
    product_org BIGINT;
BEGIN
    SELECT organization_id INTO sale_org FROM sales WHERE id = NEW.sale_id;
    IF sale_org IS NULL THEN
        RAISE EXCEPTION 'sale line references a missing sale' USING ERRCODE = '23503';
    END IF;
    IF NEW.product_id IS NOT NULL THEN
        SELECT organization_id INTO product_org FROM products WHERE id = NEW.product_id;
        IF product_org IS NULL THEN
            RAISE EXCEPTION 'sale line references a missing product' USING ERRCODE = '23503';
        END IF;
        IF sale_org <> product_org THEN
            RAISE EXCEPTION 'sale and product must belong to the same organization'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_sale_lines_tenant_guard ON sale_lines;
CREATE TRIGGER trg_sale_lines_tenant_guard
BEFORE INSERT OR UPDATE OF sale_id, product_id ON sale_lines
FOR EACH ROW EXECUTE FUNCTION dina_guard_sale_line_tenant();


CREATE OR REPLACE FUNCTION dina_guard_purchase_line_tenant()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    purchase_org BIGINT;
    product_org BIGINT;
BEGIN
    SELECT organization_id INTO purchase_org FROM purchases WHERE id = NEW.purchase_id;
    IF purchase_org IS NULL THEN
        RAISE EXCEPTION 'purchase line references a missing purchase' USING ERRCODE = '23503';
    END IF;
    IF NEW.product_id IS NOT NULL THEN
        SELECT organization_id INTO product_org FROM products WHERE id = NEW.product_id;
        IF product_org IS NULL THEN
            RAISE EXCEPTION 'purchase line references a missing product' USING ERRCODE = '23503';
        END IF;
        IF purchase_org <> product_org THEN
            RAISE EXCEPTION 'purchase and product must belong to the same organization'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_purchase_lines_tenant_guard ON purchase_lines;
CREATE TRIGGER trg_purchase_lines_tenant_guard
BEFORE INSERT OR UPDATE OF purchase_id, product_id ON purchase_lines
FOR EACH ROW EXECUTE FUNCTION dina_guard_purchase_line_tenant();


CREATE OR REPLACE FUNCTION dina_guard_cash_transaction_tenant()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    account_org BIGINT;
BEGIN
    SELECT organization_id INTO account_org
      FROM cash_accounts WHERE id = NEW.cash_account_id;
    IF account_org IS NULL THEN
        RAISE EXCEPTION 'cash transaction references a missing cash account'
            USING ERRCODE = '23503';
    END IF;
    IF NEW.organization_id <> account_org THEN
        RAISE EXCEPTION 'cash transaction and cash account must belong to the same organization'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_cash_transactions_tenant_guard ON cash_transactions;
CREATE TRIGGER trg_cash_transactions_tenant_guard
BEFORE INSERT OR UPDATE OF organization_id, cash_account_id ON cash_transactions
FOR EACH ROW EXECUTE FUNCTION dina_guard_cash_transaction_tenant();

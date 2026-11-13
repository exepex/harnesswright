package shop;

public class CustomerMapper {
    public String displayName(Customer c) {
        return c.name() == null ? "Unknown customer" : c.name().trim();
    }
}

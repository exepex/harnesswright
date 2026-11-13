package shop;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class CustomerMapperTest {
    @Test
    void nullNameIsUnknown() {
        assertEquals("Unknown customer", new CustomerMapper().displayName(new Customer(null)));
    }
}

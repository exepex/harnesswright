package shop;

public class OrderService {
    public long applyDiscount(long cents, int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("percent");
        }
        return cents - cents * percent / 100;
    }
}

pub fn parse(line: &str) -> Result<(u32, String), String> {
    let (qty, sku) = line.split_once(" x ").ok_or("no ' x '")?;
    Ok((qty.parse().map_err(|_| "bad quantity")?, sku.to_string()))
}

#[cfg(test)]
mod tests {
    #[test]
    fn parses() {
        assert_eq!(super::parse("3 x SKU-1"), Ok((3, "SKU-1".into())));
    }
}

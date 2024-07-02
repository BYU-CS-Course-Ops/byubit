from byubit import Bit


@Bit.worlds('test-white-right')
@Bit.pictures('demo-images/', ext='svg')
def main(bit):
    if bit.is_white():  # Should be true, world starts white
        bit.move()
    bit.paint('blue')
    if bit.is_white():  # Should be false, we painted blue
        bit.move()
    bit.paint('white')
    if bit.is_white():  # Should be true, we painted white
        bit.move()
    bit.paint('blue')
    if not bit.is_white():  # Should be true, we painted blue
        bit.move()


if __name__ == '__main__':
    main(Bit.new_bit)
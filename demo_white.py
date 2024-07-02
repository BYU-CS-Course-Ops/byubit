from byubit import Bit


@Bit.worlds('test-white-right', 'test-world-wrong', 'test-white-right')
@Bit.pictures('demo-images/', ext='svg')
def main(bit):
    if bit.is_white():
        bit.move()
    bit.paint('blue')
    if bit.is_white():
        bit.move()
    bit.paint('white')
    if bit.is_white():
        bit.move()
    bit.paint('blue')
    if not bit.is_white():
        bit.move()


if __name__ == '__main__':
    main(Bit.new_bit)